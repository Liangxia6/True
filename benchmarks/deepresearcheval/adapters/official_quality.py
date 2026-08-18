"""Official DeepResearchEval quality-module pointer.

Do not replace the upstream point_quality pipeline with a homemade LLM Judge.
Call Infinity-AILab/DeepResearchEval/point_quality and freeze per-task dimensions.
"""

OFFICIAL_MODULE = "point_quality"
GENERAL_DIMENSIONS = ("Coverage", "Insight", "Instruction-following", "Clarity")
SCORE_RANGE = (0.0, 10.0)
FUSE_WITH_FACT = False
