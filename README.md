# PaperFlow: Multimodal Agentic System for Translating Research Papers to Executable Code
Scientific Paper Analysis &amp; Code Generation Pipeline

## Architecture
- **Document Agent**: Parse PDFs, extract equations/figures
- **Code Agent**: Generate code from methodology sections
- **Evaluation Agent**: Compare and test generated code
- **RAG Agent**: Retrieve similar papers/implementations

## Tech Stack
- MCP for agent coordination
- Hybrid retrieval (dense + sparse)
- vLLM for model serving
- Vector DB (Qdrant/Chroma)