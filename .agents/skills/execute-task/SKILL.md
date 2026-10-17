---
name: execute-task
description: Executes tasks specified in .agents/current_task.md with strict scope discipline and verification.
---

# Execute Task Skill

Use this skill to implement instructions formulated in `.agents/current_task.md`.

## Workflow:
1. **Read Task Definition:** Open and read `.agents/current_task.md` to get the context, objectives, modified files, and implementation details.
2. **Strict Scope Discipline (Zero Scope Creep):**
   - Modify or create ONLY the files specified in the task.
   - Do not refactor unrelated code.
   - Do not add unrequested third-party dependencies or mock services.
3. **Verification:**
   - Run tests, type checks, or linter if applicable.
   - Ensure changes run without syntax errors or runtime exceptions.
4. **Report & Git Commit Command:**
   - Summarize modified files and actions taken.
   - Provide the single one-liner git command:
     `git add . && git commit -m "..." && git push origin main`
