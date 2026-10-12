"""Export a Laya checkpoint to ONNX and quantize it to int8 for on-device use.

The graph matches what laya.onnx_agent.ONNXAgent feeds and reads, so either file can be
loaded with ONNXAgent(..., onnx_path=...).

    python export_onnx.py                      # multilingual -> onnx/laya-multilingual{,-int8}.onnx
    python export_onnx.py --checkpoint english
"""

import argparse
import os
import time
from pathlib import Path

import torch

import laya

REPO = "convaiinnovations/laya"
SUBFOLDERS = {"multilingual": "multilingual", "english": None}

INPUTS = ["input_ids", "attention_mask", "marker_pos", "marker_mask", "qtype"]
OUTPUTS = ["logits", "act_logits"]
DYNAMIC_AXES = {
    "input_ids": {0: "rows", 1: "seq"},
    "attention_mask": {0: "rows", 1: "seq"},
    "marker_pos": {0: "rows", 1: "markers"},
    "marker_mask": {0: "rows", 1: "markers"},
    "qtype": {0: "rows"},
    "logits": {0: "rows", 1: "markers"},
    "act_logits": {0: "rows"},
}


class _Graph(torch.nn.Module):
    """DecisionModel.forward without the training-only `detach_encoder` argument."""

    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, input_ids, attention_mask, marker_pos, marker_mask, qtype):
        return self.model(input_ids, attention_mask, marker_pos, marker_mask, qtype)


def dummy_batch(vocab_size, seq=48):
    """A padded batch shaped like collate_items output, so dynamic axes are exercised."""
    input_ids = torch.randint(5, vocab_size, (2, seq), dtype=torch.long)
    attention_mask = torch.ones(2, seq, dtype=torch.long)
    attention_mask[1, seq // 2:] = 0
    marker_pos = torch.tensor([[10, 12, 14, 16], [8, 10, -1, -1]], dtype=torch.long)
    marker_mask = marker_pos >= 0
    qtype = torch.tensor([0, 2], dtype=torch.long)
    return input_ids, attention_mask, marker_pos, marker_mask, qtype


def mb(path):
    return os.path.getsize(path) / 1e6


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--checkpoint", choices=SUBFOLDERS, default="multilingual")
    parser.add_argument("--out", default="onnx")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(exist_ok=True)
    fp32_path = out / f"laya-{args.checkpoint}.onnx"
    int8_path = out / f"laya-{args.checkpoint}-int8.onnx"

    print(f"Loading {args.checkpoint} checkpoint...")
    agent = laya.load(REPO, subfolder=SUBFOLDERS[args.checkpoint], device="cpu")
    model = _Graph(agent.model.float().eval())
    batch = dummy_batch(agent.model.encoder.config.vocab_size)

    print(f"Exporting {fp32_path}...")
    start = time.perf_counter()
    # The head's nn.TransformerEncoderLayer otherwise runs as the fused
    # aten::_transformer_encoder_layer_fwd kernel in eval mode, which has no ONNX export.
    torch.backends.mha.set_fastpath_enabled(False)
    with torch.no_grad():
        torch.onnx.export(
            model, batch, str(fp32_path),
            input_names=INPUTS, output_names=OUTPUTS, dynamic_axes=DYNAMIC_AXES,
            opset_version=17, do_constant_folding=True, dynamo=False,
        )
    print(f"  {mb(fp32_path):.0f} MB in {time.perf_counter() - start:.0f}s")

    print(f"Quantizing to {int8_path}...")
    start = time.perf_counter()
    quantize(fp32_path, int8_path)
    print(f"  {mb(int8_path):.0f} MB in {time.perf_counter() - start:.0f}s")


def quantize(src, dst):
    """int8 weights everywhere, activations kept in float.

    Plain dynamic int8 (quantize_dynamic on MatMul) also quantizes activations at runtime, and
    ModernBERT's activation outliers do not survive that: it changed ~20% of answers. Weight-only
    8-bit MatMulNBits keeps activations in float and changes ~1%. The token embedding table (most
    of the multilingual weights, 256k vocab x 768) is a Gather, which dynamic int8 handles fine.
    """
    import onnx
    from onnxruntime.quantization import QuantType, quantize_dynamic
    from onnxruntime.quantization.matmul_nbits_quantizer import (
        DefaultWeightOnlyQuantConfig, MatMulNBitsQuantizer,
    )

    gather_path = dst.with_suffix(".gather.onnx")
    quantize_dynamic(str(src), str(gather_path), weight_type=QuantType.QInt8,
                     op_types_to_quantize=["Gather"])
    config = DefaultWeightOnlyQuantConfig(block_size=32, is_symmetric=True, bits=8,
                                          op_types_to_quantize=("MatMul",))
    quantizer = MatMulNBitsQuantizer(onnx.load(str(gather_path)), algo_config=config)
    quantizer.process()
    quantizer.model.save_model_to_file(str(dst), use_external_data_format=False)
    gather_path.unlink()


if __name__ == "__main__":
    main()
