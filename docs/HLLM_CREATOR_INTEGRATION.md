# HLLM-Creator integration

## Product decision

ByteDance HLLM-Creator is the audience intelligence foundation for the IP
Agent distribution. DeerFlow remains the only agent runtime. HLLM-Creator is
not a second agent and does not receive thread authority, platform credentials
or individual viewer identities.

The complete Apache-2.0 upstream source is pinned under
`third_party/bytedance/HLLM`. Product code must use a thin adapter or a separate
model-service process instead of copying the model implementation into
DeerFlow.

```mermaid
flowchart LR
    D["DeerFlow agent"] --> P["Full owner portfolio"]
    P --> A["Aggregate cross-platform content and outcomes"]
    A --> H["HLLM-Creator audience engine"]
    H --> E["Audience embedding and content match"]
    H --> G["Personalized hook/title/angle variants"]
    E --> R["Preflight snapshot"]
    G --> R
    R --> X["Publish via native tools"]
    X --> O["Receipt and observed outcomes"]
    O --> C["Calibration and approved training examples"]
    C --> H
```

## Boundary of responsibility

| Capability | Owner |
|---|---|
| Audience sequence encoding, dense audience representation, content-audience matching and personalized creative generation | HLLM-Creator |
| Creator expression constraints and interpretable audience projections such as Maslow/Jung/existence lenses | Thin product adapter; hypotheses remain revisable |
| Agent planning, tools, memory, browser, MCP, Skills and cross-account coordination | Native DeerFlow |
| Preflight freeze, publish receipt, observed metrics, retrospective calibration and approved-example promotion | Thin product evidence ledger |
| Image, video, speech and media finishing | Volcengine models and MediaKit |

HLLM-Creator's public example is personalized book-title generation. It is not
a CRM, publishing system, metrics collector or video pipeline. Those are
connected by DeerFlow, not reimplemented inside HLLM.

## Data adaptation

The upstream training row contract is preserved:

`user_profile`, `original_title`, `original_description`, `prompt1`,
`prompt2`, `response`, `title_list`, `item_id_list`.

`deerflow.personal_ip.hllm_creator.HLLMCreatorAdapter` produces this contract
from a chronological sequence of published content and aggregate metrics. The
adapter declares the result as an `aggregate_account_cohort`; it must never
claim that platform aggregates are person-level click histories. Raw viewer
ids, handles, contact details and raw comments are rejected at this boundary.

An account id may identify the target of a concrete data fetch or publish
receipt. It never binds a conversation or narrows the agent's portfolio.

## Runtime and packaging

The model environment stays separate from DeerFlow's backend environment.
Upstream HLLM depends on PyTorch, DeepSpeed, FlashAttention, FAISS and multiple
large language models. Its published HLLM-Creator model directory is 75.8 GB,
and the upstream reproduction script documents 64 A100 GPUs for the 1B + 8B
training run. Installing these dependencies into the Gateway would make the
ordinary customer package fragile without making DeerFlow more capable.

The customer source distribution therefore contains all model source and the
adapter, while weights are an explicitly selected model asset. Local inference
is offered only when compatible GPU capacity is detected; otherwise DeerFlow
calls a separately deployed HLLM provider. This is still one product and one
agent—only the heavy numerical runtime is isolated.

## Minimal patch policy

Keep upstream model architecture and loss functions unchanged. Product work is
limited to:

1. the aggregate Personal-IP dataset adapter (implemented);
2. a structured batch/inference service entry point instead of research CLI
   scripts;
3. explicit device and resource detection instead of hard-coded `cuda:0`;
4. optional parameter-efficient fine-tuning for a shared Personal-IP model;
5. dataset, checkpoint and evaluation version receipts.

Do not train a separate HLLM for every creator. A shared model learns across
approved, anonymized examples; each creator/account/cohort obtains its own
history-derived embedding. Full end-to-end training is a central model-building
operation, not a first-run customer requirement.

## Upstream provenance

- Source: <https://github.com/bytedance/HLLM>
- Paper: <https://arxiv.org/abs/2508.18118>
- Pinned commit: `864f17221c04a2d3082d9a072df00616bc7e6dab`
- License: Apache-2.0 (base TinyLlama/Qwen weights retain their own terms)
