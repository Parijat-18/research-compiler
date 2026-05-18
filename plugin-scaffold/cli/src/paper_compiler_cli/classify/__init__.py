ROLES = (
    "architecture_dependency",
    "loss_function_dependency",
    "dataset_dependency",
    "preprocessing_dependency",
    "evaluation_protocol_dependency",
    "baseline_dependency",
    "optimizer_or_training_trick",
    "theoretical_assumption",
    "ablation_reference",
    "engineering_reference",
    "related_work_only",
)

IMPLEMENTATION_CRITICAL = ROLES[:8]
