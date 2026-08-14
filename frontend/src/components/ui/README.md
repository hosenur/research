# UI components

This directory combines two component sources:

- Lowercase files such as `button.tsx`, `card.tsx`, and `textarea.tsx` are generated from the official Intent UI registry.
- The named AI-interface components such as `LoadingState.tsx`, `ThinkingState.tsx`, and `ApprovalCard.tsx` come from Beautiful UI. Their bundled license remains in [LICENSE](./LICENSE).

Import components directly instead of through a barrel file so Vite can keep module boundaries explicit.

```tsx
import { UiProvider } from '../components/ui/UiProvider'
import LoadingState from '../components/ui/LoadingState'

export function Example() {
  return (
    <UiProvider>
      <LoadingState />
    </UiProvider>
  )
}
```

`UiProvider` scopes the component color tokens away from the application's
paper theme and accepts a `dark` property for the dark palette.

Add missing Intent UI primitives through the registry rather than writing them manually:

```sh
cd frontend
bun x shadcn@latest add @intentui/<component>
```

Product screens may compose both component sets. `/home/hosenur/Developer/leaf` is the local reference for the established chat composition.
