# UI components

Reusable React components for the frontend live in this directory. Import
components directly instead of through a barrel file so Vite can keep module
boundaries explicit.

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

The third-party source license covering the initial component set is retained
in [LICENSE](./LICENSE).
