"""Cross-domain keyword hints for heuristic classification.

The v0.2 pipeline hardcoded ML/CS jargon (``ViT``, ``AdamW``, ``ImageNet``,
``FlashAttention``, ``CUDA``) into the classifier's hint lists. v1.0
de-biases this so the plugin works for physics, chemistry, biology,
economics, climate science — any field with implementable papers.

The default pack below is **STEM-broad**: it covers ML/CS, physics,
chemistry, biology, and applied math at the vocabulary level. Hits are
*additive* signal — absence of any matching word in the context does
NOT push the score below the section prior. So a chemistry paper that
mentions no ML jargon still gets the +0.4 method-section prior; the
heuristic just contributes less when no domain hints fire, leaving the
LLM-residual classifier (Phase 4 ``LLM_THRESHOLD``) to do the precise
work.

Swapping packs
--------------

Users can replace this module wholesale with their own keyword sets by
pointing ``cfg.compile.domain_patterns_module`` at an import path. The
required public names are the same as below:

    METHOD_HINTS, OBJECTIVE_HINTS, DATA_HINTS, PREPROCESSING_HINTS,
    EVALUATION_HINTS, BASELINE_HINTS, PROCEDURE_HINTS, THEORY_HINTS,
    ABLATION_HINTS, ENGINEERING_HINTS, CONTRADICTS_HINTS,
    DOMAIN_TITLE_HINTS (role -> tuple[str])

The deprecated v0.2 aliases (``ARCH_HINTS`` etc.) are re-exported below
so existing call sites that imported the old names keep working until
v1.1 cleanup.
"""

from __future__ import annotations

# --- method (algorithmic / structural unit) ---
# ML: architectures + layers. Physics: numerical schemes. Chemistry:
# synthesis routes. Biology: protocols. Math: algorithms.
METHOD_HINTS = (
    # ML/CS
    "architecture", "encoder", "decoder", "transformer", "attention",
    "backbone", "block", "module", "layer", "network", "head",
    # Physics / numerical methods
    "scheme", "integrator", "solver", "discretization", "lattice",
    "mesh", "grid", "ensemble",
    # Chemistry / biology
    "synthesis", "reaction", "protocol", "pipeline", "assay", "pathway",
    # Math
    "algorithm", "procedure", "routine", "method",
)

# --- objective (function being optimized / measured / maximized) ---
OBJECTIVE_HINTS = (
    # ML
    "loss", "objective", "log-likelihood", "regulariz", "kl",
    "cross-entropy", "contrastive", "reward", "penalty",
    # Physics
    "hamiltonian", "lagrangian", "action", "energy function",
    "free energy", "potential", "partition function",
    # Chemistry / biology
    "yield", "selectivity", "binding affinity", "fitness",
    # Math
    "cost", "loss function", "minimization", "maximization",
)

# --- data (inputs / measurements / samples / corpus) ---
DATA_HINTS = (
    # ML
    "dataset", "corpus", "benchmark", "split", "training set",
    "test set", "validation",
    # Physics / chem / bio
    "measurement", "observation", "sample", "specimen", "snapshot",
    "trajectory", "trace", "spectrum", "image stack", "sequence",
    "compound", "molecule", "patient", "cohort",
    # Generic
    "data",
)

# --- preprocessing (transformation step on data) ---
PREPROCESSING_HINTS = (
    "preprocess", "tokeniz", "augment", "normaliz", "patchif", "embed",
    "filter", "denoise", "downsamp", "upsamp", "rescale", "standardiz",
    "calibrat", "background subtract", "imputation", "alignment",
)

# --- evaluation (how outputs are measured / judged) ---
EVALUATION_HINTS = (
    # ML
    "evaluat", "metric", "benchmark", "score", "accuracy",
    # Physics / chem / bio
    "convergence", "diagnostic", "validation", "fidelity",
    "verification", "cross-validation", "spectra", "chromatograph",
    # Generic
    "performance", "criterion", "test against", "compare to",
)

# --- baseline (prior method used as comparison) ---
BASELINE_HINTS = (
    "baseline", "we compare", "outperform", "against", "previous best",
    "prior method", "control", "standard", "reference method",
)

# --- procedure (training / simulation / solving / experimental procedure) ---
# Captures the *how-it-runs* layer. Was "optimizer + training tricks"
# in v0.2.
PROCEDURE_HINTS = (
    # ML
    "adam", "sgd", "warmup", "schedule", "learning rate", "lr",
    "mixed precision", "ema", "weight decay", "training step",
    "training loop", "fine-tune", "distill",
    # Physics
    "integrator", "time step", "monte carlo", "molecular dynamics",
    "annealing", "thermostat", "barostat", "trotter",
    # Chemistry / biology
    "reaction conditions", "incubation", "centrifuge", "pcr cycle",
    "wash step", "elution",
    # Generic
    "iteration", "step size", "tolerance",
)

# --- theory (theoretical foundation / assumption / theorem) ---
THEORY_HINTS = (
    "theorem", "lemma", "proof", "assumption", "convergence",
    "bound", "inequality", "corollary", "conjecture", "axiom",
    "hypothesis", "principle", "law", "invariant",
)

# --- ablation reference ---
ABLATION_HINTS = (
    "ablation", "we ablate", "removing", "without the", "with vs without",
    "leave-one-out",
)

# --- engineering (implementation / framework / library) ---
ENGINEERING_HINTS = (
    # ML/CS
    "pytorch", "tensorflow", "jax", "cuda", "flashattention",
    "deepspeed", "library", "framework", "implement", "codebase",
    "repository",
    # Physics / chem / bio software
    "lammps", "gromacs", "vasp", "openmm", "gromos", "amber",
    "gaussian", "psi4", "scipy", "numpy",
    # Generic engineering
    "compile", "build system", "ci/cd", "wrapper",
)

# --- contradicts (negation / refutation cues near a citation) ---
CONTRADICTS_HINTS = (
    "unlike", "in contrast", "however", "we disagree", "refute",
    "contradict", "fails to", "fail to", "does not", "cannot",
    "outperform", "worse than", "differs from", "instead of",
    "contrary to", "counter to",
)

# --- per-role title-prior hints ---
# Used by classify/heuristic.py to add a small boost when a *cited paper's
# title* contains a word strongly associated with a particular role. The
# old hardcoded list was ML-only ("transformer / attention / encoder" →
# architecture). The map below is per-role, domain-neutral, and kept
# small so titles like "Attention is all you need" still trigger sanely.
DOMAIN_TITLE_HINTS: dict[str, tuple[str, ...]] = {
    "data_dependency": (
        "dataset", "corpus", "benchmark", "samples", "measurements",
    ),
    "procedure_dependency": (
        "optimizer", "training", "annealing", "monte carlo",
        "molecular dynamics", "integrator", "scheduler", "solver",
    ),
    "method_dependency": (
        "transformer", "attention", "encoder", "network", "algorithm",
        "scheme", "method", "framework", "system",
    ),
    "theory_dependency": (
        "theorem", "convergence", "bound", "principle", "law", "axiom",
    ),
    "evaluation_dependency": (
        "evaluation", "metric", "benchmark", "convergence diagnostic",
    ),
    "baseline_dependency": (
        "baseline", "reference",
    ),
}


# ---------------------------------------------------------------------------
# Backwards-compat aliases (deprecated v0.2 names). Imports of these in
# classify/heuristic.py keep working through v1.0 → v1.1 cleanup.
# ---------------------------------------------------------------------------
ARCH_HINTS = METHOD_HINTS
LOSS_HINTS = OBJECTIVE_HINTS
DATASET_HINTS = DATA_HINTS
PREPROC_HINTS = PREPROCESSING_HINTS
EVAL_HINTS = EVALUATION_HINTS
OPT_HINTS = PROCEDURE_HINTS
ENG_HINTS = ENGINEERING_HINTS
