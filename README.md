# autoankicard

Local AI vocabulary card generator for Anki.

## Configuration

This project is set up to use SiliconFlow with the `deepseek-ai/DeepSeek-V3.2` model.

Create a `.env` file in the project root with the following values:

```env
SILICONFLOW_API_KEY=your_api_key_here
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
LLM_MODEL=deepseek-ai/DeepSeek-V3.2
```

For safety, `.env` is ignored by git. If you need a template, use `.env.example`.
