# Known bugs

Known-broken behaviour in the web app that has not been fixed. Each entry says what is
wrong, how to reproduce it, why it has gone unnoticed, and what fixing it would involve.

A bug leaves this file when it is fixed — and the test that pins the broken behaviour
should be inverted rather than deleted, so the fix is what makes it pass.

---

## Sidebar nav sub-items never render

**Status:** open. Dormant — nothing in the template triggers it.
**Where:** `packages/components/src/layout/nav-sidebar.tsx:27-66` (`MenuNavigator`)
**Pinned by:** `packages/components/src/layout/nav-sidebar.test.tsx` →
`"does not render sub-items: the panel is closed and has no trigger"`

### What is wrong

A `NavItem` with an `items` array takes the collapsible branch, which renders its
sub-items inside `<CollapsibleContent>`. They never appear, and nothing the user can do
will make them appear.

Base UI's `Collapsible` opens via one of three things: a `defaultOpen` prop (uncontrolled,
starts open), a controlled `open` prop, or a `CollapsibleTrigger` inside it that the user
clicks. `MenuNavigator` supplies **none** of them:

```tsx
<Collapsible key={item.title} className="group/collapsible">
```

`CollapsibleContent` is Base UI's `Panel`, whose `keepMounted` defaults to `false`; it
renders only when `keepMounted || hiddenUntilFound || mounted`. Closed with no way to
open means the sub-items produce no DOM at all — this is not a styling or z-index problem.

`CollapsibleTrigger` is exported from `packages/ui/src/index.ts` and imported nowhere.

### Reproducing it

Give any nav item an `items` array:

```ts
export const HUB_NAV: NavItem[] = [
  {
    title: "Home",
    url: "/home",
    icon: HomeIcon,
    items: [{ title: "Reports", url: "/home/reports" }],
  },
]
```

The "Home" entry renders and links correctly. "Reports" is absent from the DOM. The
rendered `[data-slot="collapsible"]` element carries `data-closed=""`.

### Why nobody noticed

`HUB_NAV` (`apps/web/src/lib/hub-nav.ts`) has a single flat entry, and its commented-out
example is flat too. Nothing in the repo has ever constructed a `NavItem` with sub-items,
so the branch has never executed. `NavItem.items` is part of the public type
(`packages/core/src/types/nav.ts`), which makes this a likely early step for a fork adding
second-level navigation.

### Fixing it

Pick the intended behaviour first — these are genuinely different products:

| Option | Behaviour | Cost |
|---|---|---|
| `defaultOpen` | Sub-items always visible; the group never collapses | One prop |
| `defaultOpen={isActive}` | The active section expands, others stay shut | One prop; probably the original intent |
| Add a `CollapsibleTrigger` | A real toggle the user controls | A new control, plus the caveat below |

There is a second-order problem for the trigger option: the top-level item is wrapped in
`<Link href={item.url}>`, so clicking it navigates. A chevron would have to be a separate
control beside the link, not the link itself — which also means deciding what a parent
item's own `url` means once it has children.

Whichever is chosen, invert the test named above; it currently asserts the broken
behaviour on purpose.
