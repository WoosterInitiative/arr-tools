## Agent Loop Boundaries
1. DO NOT run linting or formatting tools (e.g., ESLint, Prettier); the user will handle formatting.
2. If a multi-step fix or improvement fails a test, do not attempt to auto-correct it sequentially more than once.
3. If you get stuck, encounter a complex regression, or require a second iteration loop, PAUSE immediately.
4. State clearly:
   - What has been successfully changed so far.
   - Where the code is currently failing or stuck.
   - Specific locations/files where the user should begin looking to resolve it.
