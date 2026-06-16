# Project Instructions: JewelScope Research

## Context Management
- **Auto-Compaction**: This project has been configured with a `.gemini/settings.json` file to enable automatic context compaction (threshold: 0.5). This ensures that long conversations are automatically summarized to maintain performance and stay within model limits, similar to the Antigravity CLI's default behavior.
- **Manual Compaction**: You can still use the `/compact` command if you feel the context is becoming too noisy.
- **Narrative Flow**: Use the `update_topic` tool to maintain a running summary of progress. This serves as an additional layer of context management.
