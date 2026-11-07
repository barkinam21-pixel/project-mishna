# ComfyUI adapter — partial implementation, 2026-11-07

Implemented `tools/comfy_image_backend.py`: network-free manifest planning, reference hash/rights checks, stable specification keys, duplicate-ID rejection and a ComfyUI `/prompt` + `/history` transport. One endpoint interface supports loopback or HTTPS cloud endpoints. Submission requires explicit authorization and verified zero-cost compute. POST is not retried after uncertain failure.

Six offline tests pass. No actual ComfyUI server, GPU, model weights, image generation or paid endpoint was used. Runtime configuration reports no GPU capability or provider binding. This is not evidence that free automatic GPU hosting is available.

Not yet implemented: workflow compiler/model-specific reference nodes, authenticated cloud transport, image retrieval, persisted accepted-only cache, character continuity review, renderer asset intake and hosted generation workflow. Specification hashes alone are NOT a working asset cache. Human continuity approval is still required; seed alone cannot lock identity.

Model selection/licence and hardware requirements have NOT been verified in this implementation. Do not download weights or treat any model as cleared for publication. A local GPU would require separately installed ComfyUI, compatible weights and reference workflow; a cloud GPU would additionally require authorized zero-cost compute and private storage. Nothing was installed on Bar's computer.

The approved combined visual direction and Alnilam baseline remain unchanged. No fal.ai calls, charges, merge, publication or generated artwork. This adapter is preparatory code, not a completed autonomous seven-image production engine.
