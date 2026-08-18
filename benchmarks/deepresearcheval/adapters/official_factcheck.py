"""Official DeepResearchEval fact-checking-module pointer.

Labels remain Right / Wrong / Unknown. Unknown is neither FAIL nor PASS.
Do not invent claims that the official extractor did not produce.
"""

OFFICIAL_MODULE = "factual_eval"
LABELS = ("Right", "Wrong", "Unknown")
FACT_RATIO = "N_Right / N_Statements"
REPORT_WITH = ("statement_density", "right_count", "wrong_count", "unknown_count")
FUSE_WITH_QUALITY = False
