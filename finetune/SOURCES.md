# Data source research (2026-10-12)

Candidates for growing the dataset beyond VNHSGE and M3Exam, with what each allows. "Robots" is
what the site's robots.txt says for generic crawlers; none of the sites below names AI crawlers.

## Ready-made datasets

| Source | Content | Size | License / access | Verdict |
|---|---|---|---|---|
| [hllj/vi_grade_school_math_mcq](https://huggingface.co/datasets/hllj/vi_grade_school_math_mcq) (**added**, 7,095 usable) | Math MCQ, grades 1–5, with explanations ("Đáp án đúng là: C") | 2,733 exercise sets, several questions each | No license; scraped from VietJack (`vietjack.json`) | Fills the primary math gap, but carries VietJack's copyright. Personal research only. |
| [ViMMRC 2.0](https://github.com/sonlam1102/vimmrc2) | Reading comprehension from Tiếng Việt / Văn textbooks, grades 1–12 | 699 passages, 5,273 questions | Research only, signed agreement emailed to sonlt@uit.edu.vn | Best fit for primary and literature. Request it. |
| [VMLU Vi-MQA](https://vmlu.ai) | 58 subjects incl. elementary math/science, middle and high school | 10,880 | MIT repo; download needs a vmlu.ai login; test answers hidden | Only dev/valid answers usable for training. Log in and download. |
| ViEduQA ([shnl collection](https://huggingface.co/collections/shnl/vieduqa-datasets)) | Biology 2.85k, history 5.88k, geography 2.62k, civics 1.27k | ~12.6k | Not accessible to us yet (gated or other names); HF was rate-limiting | Probably high-school level and overlapping VNHSGE. Check when HF unblocks. |
| [ViMath-Bench](https://aclanthology.org/2024.conll-1.20/) (CoNLL 2024) | Elementary math | ~8k | Not found yet; ask the authors | Follow up. |
| [VMMU / ViExam](https://arxiv.org/html/2508.13680) | Grade 12 exams, driving, IQ | 2,548 | CC BY 4.0 | Skip: 93% need an image, shipped as page images. |

## Official sources

| Source | Content | Robots | Verdict |
|---|---|---|---|
| [moet.gov.vn](https://moet.gov.vn) | Answer keys only, as scanned PDFs in a public Google Drive folder (2026: 12 subjects). The exam papers themselves are not published as text | Disallows crawling `*.pdf`, `*.doc(x)` | Keys alone are useless. Needs the exam papers from news sites (photos), OCR or manual transcription, then matching each exam code (mã đề) to its key. Since 2025 only Part I is 4-option multiple choice. |

## Commercial exam and homework sites

| Site | Robots | Terms on copying |
|---|---|---|
| loigiaihay.com | Allows all except rating/comment endpoints | Policy page says nothing on copying |
| khoahoc.vietjack.com | Allows except search, exam results, log viewer | Copyright page: content is VietJack's; contact for takedown |
| vietjack.com | No robots.txt (404) | Same copyright page |
| hoc247.net | Allows except taking exams, account pages | Not found |
| tuyensinh247.com | Allows, with a long list of blocked pages | Forbids using, distributing or transferring its intellectual property in any form without permission |
| vndoc.com | Allows all | Forbids sharing works without the rights holder's consent |
| olm.vn | Allows except admin/account pages | Not checked |

Robots.txt allowing a crawl is not permission to reuse the content: the questions and explanations
are copyrighted by the sites (or the textbook publishers they copy from). Keep anything crawled
local, for research, never redistributed or used in a paid product.
