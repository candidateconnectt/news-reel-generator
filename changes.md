# Performance Optimization Task (No Functional Changes)

The reel/post generator is already fully functional.

DO NOT redesign, rewrite, or restructure the application.

DO NOT change business logic.

DO NOT modify working features.

DO NOT alter frontend behavior.

DO NOT change API contracts.

Your task is ONLY to improve video generation performance, rendering speed, scalability, and resource utilization.

---

## Current Situation

The application already:

* Generates scripts
* Retrieves videos from Pexels
* Generates voice using Edge-TTS
* Creates captions
* Produces final reels/videos successfully

The functionality is correct.

The problem is that video generation and rendering are taking too much time.

The goal is optimization only.

---

## Required Approach

First analyze the current video generation pipeline and identify:

1. Bottlenecks
2. Blocking operations
3. Sequential tasks that can run concurrently
4. Slow rendering steps
5. MoviePy usage (if present)
6. FFmpeg opportunities

Before making changes, explain:

* Current workflow
* Bottlenecks found
* Exact optimizations proposed
* Files that will be modified

---

## Optimization Goals

### Goal 1: Replace Slow Video Operations

If MoviePy is being used for heavy video processing:

* merging
* concatenation
* resizing
* subtitle burning
* audio insertion

Prefer FFmpeg where appropriate.

Only replace performance bottlenecks.

Do not rewrite working functionality unnecessarily.

---

### Goal 2: Make Video Processing Non-Blocking

If any rendering operation blocks execution:

Replace blocking execution with asynchronous subprocess execution.

Preferred approach:

* asyncio.create_subprocess_exec()
* asynchronous FFmpeg execution

The application should remain responsive during rendering.

---

### Goal 3: Parallelize Independent Tasks

Analyze the workflow.

If tasks can safely run in parallel, use concurrency.

Examples:

* downloading multiple Pexels videos
* preparing assets
* generating metadata

Use asyncio.gather() where beneficial.

Do not introduce race conditions.

---

### Goal 4: Reduce Render Time

Review FFmpeg commands and rendering settings.

Optimize for faster processing while maintaining acceptable output quality.

Avoid unnecessary encoding passes.

Avoid duplicate processing.

Avoid temporary file creation where possible.

---

### Goal 5: Improve Scalability

Ensure the system can handle multiple video-generation requests efficiently.

Focus on:

* memory usage
* CPU utilization
* async execution
* resource cleanup

Do not introduce breaking architectural changes.

---

## Important Constraints

The system already works.

Treat this as a performance optimization task only.

Do not:

* rewrite the application
* change project structure unnecessarily
* rename modules without reason
* modify unrelated code
* change frontend logic
* change existing API responses

Only touch code that directly impacts rendering performance.

---

## Expected Output

1. Explain current bottlenecks.
2. Explain proposed optimizations.
3. Implement optimizations.
4. Summarize performance improvements.
5. List every modified file.
6. Confirm that no functionality was changed.

Primary objective:

Keep behavior identical.

Make rendering faster, more asynchronous, and more scalable.
