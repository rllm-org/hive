"use client";

import { RenderMessage } from "@/components/chat/render-message";

const TEST_MESSAGE = `Here's some **bold** and *italic* text with \`inline code\`.

## Code block with syntax highlighting

\`\`\`python
def fibonacci(n: int) -> int:
    if n <= 1:
        return n
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b

print(fibonacci(10))
\`\`\`

## A markdown table

| Model | Score | Latency |
|-------|-------|---------|
| GPT-4 | 0.92 | 1.2s |
| Claude | 0.95 | 0.8s |
| Gemini | 0.88 | 1.5s |

## CSV data

\`\`\`csv
epoch,train_loss,val_loss,accuracy
1,2.3,2.5,0.42
2,1.8,2.1,0.58
3,1.2,1.5,0.71
4,0.8,1.1,0.79
5,0.5,0.9,0.84
\`\`\`

## A chart

\`\`\`chart
{
  "type": "line",
  "title": "Training Progress",
  "x": "epoch",
  "y": ["train_loss", "val_loss"],
  "data": [
    {"epoch": 1, "train_loss": 2.3, "val_loss": 2.5},
    {"epoch": 2, "train_loss": 1.8, "val_loss": 2.1},
    {"epoch": 3, "train_loss": 1.2, "val_loss": 1.5},
    {"epoch": 4, "train_loss": 0.8, "val_loss": 1.1},
    {"epoch": 5, "train_loss": 0.5, "val_loss": 0.9}
  ]
}
\`\`\`

## Mermaid diagram

\`\`\`mermaid
graph LR
    A[Baseline] --> B[CoT k=3]
    B --> C[CoT k=5]
    C --> D[+ Self-consistency]
    D --> E[Best: 0.92]
\`\`\`

## Math

The cross-entropy loss is $L = -\\sum_{i} y_i \\log(\\hat{y}_i)$ and the gradient is:

$$\\nabla_\\theta J(\\theta) = \\mathbb{E}_{\\pi_\\theta} \\left[ \\sum_{t=0}^{T} \\nabla_\\theta \\log \\pi_\\theta(a_t|s_t) \\cdot R_t \\right]$$

## Blockquote

> This is a blockquote with **bold** inside it.

## Lists

- First item
- Second item
- Third item

1. Numbered one
2. Numbered two
3. Numbered three
`;

export default function TestArtifactsPage() {
  return (
    <div style={{ maxWidth: 700, margin: "40px auto", padding: "0 20px", fontFamily: "var(--font-dm-sans)" }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 24 }}>Artifact Rendering Test</h1>
      <div style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: 8, padding: 16 }}>
        <RenderMessage
          text={TEST_MESSAGE}
          validatedMentions={[]}
          renderMention={() => null}
        />
      </div>
    </div>
  );
}
