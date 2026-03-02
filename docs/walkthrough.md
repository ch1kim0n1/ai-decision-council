# Interactive Walkthrough Guide

## Complete End-to-End Example

This guide walks through a realistic use case: **Evaluating a tech decision** using the council.

---

## Scenario: Should We Migrate to Microservices?

Let's run the council to get a multi-angle perspective on this architectural decision.

### Step 1: Setup

```bash
# Install
pip install "ai-decision-council[api]"

# Configure
export LLM_COUNCIL_API_KEY="your-openrouter-key"
export LLM_COUNCIL_MODEL_COUNT=5
```

### Step 2: Interactive Python Session

```python
from ai_decision_council import Council

# Initialize council
council = Council.from_env()

# Our question
question = """
We're a 50-person startup currently on a monolithic architecture.
Should we migrate to microservices? Consider:
- Current team size and skills
- Product lifecycle stage
- Operational complexity
- Time and cost to migrate
Give a balanced recommendation.
"""

# Run the council
print("Starting council deliberation...")
result = council.run_sync(question)
```

---

## Understanding the Output

### Stage 1: Individual Expert Opinions

After the council runs, let's examine Stage 1 responses:

```python
print("=" * 70)
print("STAGE 1: What Each Model Thinks")
print("=" * 70)

for i, response in enumerate(result.stage1, 1):
    model = response['model'].split('/')[-1]  # "gpt-5.1" from "openai/gpt-5.1"

    print(f"\n{i}. {model}")
    print("-" * 70)
    print(response['response'])
    print()
```

**Sample Output:**

```
1. gpt-5.1
------------------------------------------------------
Migration to microservices makes sense if:
- You have 5+ teams that can own separate services
- Your traffic patterns support distributed architecture
- You have ops expertise (or plan to hire it)

For a 50-person startup:
✅ Pros: Better scalability, independent deployment
❌ Cons: 6-12 months migration, increased operational overhead

Recommendation: Wait until you hit...

2. claude-sonnet-4.5
------------------------------------------------------
With 50 people, you're at an inflection point. Consider:

1) Your burn rate on infrastructure
   - Monolith: Simple to operate
   - Microservices: Requires container orchestration

2) Team structure
   - Do you have dedicated ops/SRE?
   - Can frontend, backend, data teams work independently?

3) Competitive pressure
   - Does your product need faster iteration?

Recommendation: Phase migration...

3. gemini-3-pro-preview
------------------------------------------------------
Technical assessment:
Your monolith probably works fine today. Migration is a business...
```

### Stage 2: Models Peer Review Each Other

Now see how the models ranked each other's responses:

```python
print("=" * 70)
print("STAGE 2: What Models Think of Each Other")
print("=" * 70)

# Get the label→model mapping (anonymous in original, revealed here)
label_to_model = result.metadata['label_to_model']

for i, ranking in enumerate(result.stage2, 1):
    model = ranking['model'].split('/')[-1]

    print(f"\n{model}'s Ranking:")
    print("-" * 70)

    # Show the raw ranking (with de-anonymized names for readability)
    ranking_text = ranking['ranking']
    for label, real_model in label_to_model.items():
        model_short = real_model.split('/')[-1]
        ranking_text = ranking_text.replace(label, f"**{model_short}**")

    print(ranking_text)
    print(f"\nParsed order: {ranking['parsed_ranking']}")
```

**What this reveals:**

- Which arguments convinced other models
- Which responses were seen as most balanced
- Areas of disagreement

### Stage 3: Chairman Synthesizes Final View

```python
print("=" * 70)
print("STAGE 3: Final Recommendation")
print("=" * 70)
print("\n" + result.final_response)
```

### Metadata: Consensus Scores

```python
import json

print("=" * 70)
print("CONSENSUS: How Models Ranked Each Other")
print("=" * 70)

aggregates = result.metadata['aggregate_rankings']

print("\n📊 Aggregate Rankings (scored by peer review):\n")
for model, scores in aggregates.items():
    model_short = model.split('/')[-1]
    avg_position = scores['avg_position']

    # Lower position = more highly ranked
    rank_emoji = "🏆" if avg_position <= 1.5 else "✅" if avg_position <= 2.5 else "👍"

    print(f"{rank_emoji} {model_short:20} Avg position: {avg_position:.2f} "
          f"(votes: {scores['votes']})")
```

**Interpretation:**

```
🏆 gpt-5.1           Avg position: 1.33 (votes: 5)    ← Most highly ranked
✅ claude-sonnet-4.5 Avg position: 2.17 (votes: 5)    ← Consensus strong
👍 gemini-3          Avg position: 2.50 (votes: 5)    ← Still respected
```

This tells you:

- Models somewhat agreed GPT-5.1 gave the best balanced view
- But Claude and Gemini also contributed valuable perspectives

---

## Checking for Errors

```python
if result.errors:
    print(f"\n⚠️  {len(result.errors)} model(s) encountered errors:\n")

    for error in result.errors:
        print(f"❌ {error.model} (Stage {error.stage})")
        print(f"   Error: {error.error_code}")
        print(f"   Message: {error.message}\n")
else:
    print("\n✅ All models completed successfully!")
```

**Possible errors:**

- One model timed out → Continue with other responses (robust!)
- Rate limit hit → Auto-retry with backoff
- Invalid API key → Full failure (all or nothing at beginning)

---

## Using the Output Programmatically

### Option 1: Extract Just the Final Answer

```python
# If you only care about the synthesis
final_answer = result.final_response
# Now use this in your application
send_to_stakeholders(final_answer)
```

### Option 2: Store Full Output for Audit

```python
import json
from datetime import datetime

# Save complete council deliberation
audit_record = {
    "timestamp": datetime.now().isoformat(),
    "question": question,
    "council_size": len(result.stage1),
    "models_used": [r['model'] for r in result.stage1],
    "full_result": result.to_dict(),
    "decision": result.final_response
}

# Save to database or file
with open(f"decision_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", "w") as f:
    json.dump(audit_record, f, indent=2)
```

### Option 3: Create a Report

```python
from datetime import datetime

def create_decision_report(result, question):
    """Generate a formatted decision report."""

    report = f"""
    COUNCIL DECISION REPORT
    Generated: {datetime.now().isoformat()}

    QUESTION:
    {question}

    ════════════════════════════════════════════════════════════════
    COUNCIL COMPOSITION
    ════════════════════════════════════════════════════════════════
    {len(result.stage1)} expert models provided perspectives:
    {chr(10).join(f"  • {r['model'].split('/')-1}" for r in result.stage1)}

    ════════════════════════════════════════════════════════════════
    CONSENSUS RECOMMENDATIONS (Score = how other models ranked it)
    ════════════════════════════════════════════════════════════════
    """

    # Sort by consensus
    scored = sorted(
        result.metadata['aggregate_rankings'].items(),
        key=lambda x: x[1]['avg_position']
    )

    for rank, (model, scores) in enumerate(scored, 1):
        report += f"\n{rank}. {model.split('/')[-1]:25} (Avg score: {scores['avg_position']:.2f})"

    report += f"\n\n════════════════════════════════════════════════════════════════\n"
    report += f"FINAL RECOMMENDATION\n"
    report += f"════════════════════════════════════════════════════════════════\n"
    report += result.final_response

    return report

# Generate and display
report = create_decision_report(result, question)
print(report)

# Save report
with open("decision_report.txt", "w") as f:
    f.write(report)
```

---

## Async Example: Running in an Application

```python
import asyncio
from fastapi import FastAPI
from ai_decision_council import Council

app = FastAPI()
council = Council.from_env()

@app.post("/analyze")
async def analyze_decision(request_data: dict):
    """Endpoint that runs council analysis."""

    question = request_data.get("question")

    # Run council asynchronously (doesn't block other requests)
    result = await council.run(question)

    # Return synthesized answer
    return {
        "answer": result.final_response,
        "confidence_score": calculate_confidence(result),
        "models_used": len(result.stage1),
        "errors": len(result.errors)
    }

def calculate_confidence(result):
    """
    Quick confidence metric:
    - All models agree (low variance in rankings) = high confidence
    - Models disagree = lower confidence
    """
    aggregates = result.metadata['aggregate_rankings']
    positions = [s['avg_position'] for s in aggregates.values()]

    # Low standard deviation = agreement
    import statistics
    variance = statistics.stdev(positions)

    # Convert to 0-1 confidence
    confidence = max(0, min(1, 1 - (variance / 5)))
    return round(confidence, 2)

# Usage
# curl -X POST http://localhost:8000/analyze \
#   -H "Content-Type: application/json" \
#   -d '{"question": "Should we use Kubernetes?"}'
```

---

## Frontend Integration Example

```python
# In a FastAPI route, stream council progress to frontend
from fastapi.responses import StreamingResponse
import json

@app.post("/council/stream")
async def council_stream(req: dict):
    """Stream council stages as events to frontend."""

    async def event_generator():
        council = Council.from_env()

        # Stage 1 responses come in
        async for response in stream_stage1(council, req["question"]):
            yield f"data: {json.dumps({
                'stage': 1,
                'model': response['model'],
                'response': response['response']
            })}\n\n"

        # Stage 2 rankings come in
        for ranking in result.stage2:
            yield f"data: {json.dumps({
                'stage': 2,
                'model': ranking['model'],
                'ranking': ranking['parsed_ranking']
            })}\n\n"

        # Stage 3 final answer
        yield f"data: {json.dumps({
            'stage': 3,
            'answer': result.final_response
        })}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )
```

**Frontend JavaScript to consume:**

```javascript
const eventSource = new EventSource("/council/stream", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
});

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);

  if (data.stage === 1) {
    // Show individual response
    addModelResponse(data.model, data.response);
  } else if (data.stage === 2) {
    // Update ranking
    showRankings(data.model, data.ranking);
  } else if (data.stage === 3) {
    // Show final answer
    displayFinalAnswer(data.answer);
    eventSource.close();
  }
};
```

---

## Troubleshooting During Walkthrough

### "All models timed out"

```python
# Your timeout is too aggressive
# Try:
config = CouncilConfig.from_env()
config.stage_timeout_seconds = 180  # Increase from default 120
```

### "Rate limited"

```python
# OpenRouter is rate limiting you
# The system auto-retries, but check:
# 1. How many concurrent requests are you making?
# 2. Do you have a premium OpenRouter account?
# 3) Consider caching responses to identical questions
```

### "One model consistently fails"

```python
# That model might not be available on your OpenRouter plan
# Remove it and use a different one

config = CouncilConfig.from_env(
    models=["openai/gpt-5.1", "anthropic/claude-sonnet-4.5", "google/gemini-3-pro-preview"]
    # Skip the problematic model
)
```

### Cost is too high

```python
# Use cheaper models
config = CouncilConfig.from_env(
    models=["anthropic/claude-3.5-haiku", "google/gemini-1.5-flash", "meta-llama/llama-3.2-8b"],
    model_count=3  # Fewer models
)
# Should reduce cost by 90%+
```

---

## Next Steps

1. **Try different questions** - See how council behaves on various topics
2. **Compare: single model vs. council** - Do you see value in peer review?
3. **Integrate into your application** - Use async/streaming for better UX
4. **Configure for your use case** - Tune model count, timeouts, models
5. **Monitor costs** - Track API spending if running in production
6. **Add caching** - Don't run council on identical questions

See other docs:

- [Use Cases](use-cases.md) - When to use council
- [Performance Benchmarks](performance-benchmarks.md) - Speed/cost expectations
- [Deployment Guide](deployment.md) - Running in Kubernetes
- [API Reference](api-reference.md) - Full API documentation
