# Repository instructions

## Frontend UI policy

- Do not create new UI primitives or hand-style interactive controls.
- Compose product screens from the installed Intent UI components in `frontend/src/components/ui` and the licensed Beautiful UI components in that same directory.
- Use `/home/hosenur/Developer/leaf` as the reference for combining Intent UI with Beautiful UI, especially for agent chat composition and interaction patterns.
- When a required primitive is missing, install it from the Intent UI registry before using it. Run `bun x shadcn@latest add @intentui/<component>` from `frontend/`; do not recreate the component manually.
- Keep `frontend/components.json`, the registry-generated `frontend/src/lib/primitive.ts`, and registry-generated component source under version control.
- Preserve component provenance and bundled third-party licenses. Do not copy licensed fonts or assets from Leaf.
- Semantic HTML for document content and layout is allowed. Interactive controls must use the installed component system.
- Use `@heroicons/react/24/solid` for product icons. Do not add Lucide, Iconoir, or another icon library.
- Consult `https://intentui.com/llms.txt` and `https://www.beautifului.dev/` when choosing components or patterns.

## Validation policy

- Do not add or run tests unless the user explicitly asks for tests.
- Production builds and static type checks are allowed for validating implementation work.

## Deployment policy

- Deploy application code to Railway through the connected Git repository. Commit and push code changes so Railway's Git integration performs the deployment; do not upload code directly with `railway up` or `railway deployment up`.
- The Railway CLI may still be used for infrastructure configuration, variables, status, logs, metrics, and deployment diagnostics.

## Frontend data policy

- Put component state and side-effect lifecycles behind React hooks.
- Use SWR hooks for HTTP server state: `useSWR` for reads and polling, and `useSWRMutation` for user-triggered mutations.
- Keep raw request orchestration out of route and product components. Wrap special transports such as upload-progress XHR in a reusable hook.
- TanStack AI streaming remains owned by its `useChat` hook; do not force AG-UI streams through SWR.
