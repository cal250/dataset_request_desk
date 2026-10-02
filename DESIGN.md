# Dataset Request Desk: Product Design Direction

## Purpose

This document defines the visual and interaction standard for Dataset Request Desk. The application is an internal operations tool for clients, data-collection operators, and administrators. It should feel trustworthy, fast, calm, and deliberately designed for repeated work.

HTMX is an interaction strategy, not a visual style. Server-rendered pages and partial updates must have the same quality bar as a polished SaaS operations product.

## Design Principle

Follow the design language of **focused B2B operations software**:

- Information-dense enough for people who work in the product repeatedly.
- Clear hierarchy, calm surfaces, and restrained color.
- Tables, filters, compact forms, and inline actions instead of oversized marketing sections.
- A status-oriented workflow where a user can understand what requires attention in seconds.
- Useful empty, loading, error, and permission-denied states.

This is not a landing page. The first authenticated screen is immediately useful work: a request list with its filters, statuses, and next actions visible.

### Primary Reference: Linear

Linear is the primary design reference for interaction quality and information hierarchy. We take inspiration from its compact sidebar, quiet surfaces, high-density lists, readable status signals, focused detail views, and preference for getting out of the user's way.

We do **not** copy Linear's logo, brand identity, exact layout, wording, colors, or proprietary visual assets. Dataset Request Desk has its own teal-and-slate visual system and is shaped around robotics-data fulfilment rather than software issue tracking.

Use Linear-inspired patterns in this application:

- A stable navigation shell that leaves maximum room for work.
- A list-first request workspace where filtering and scanning are fast.
- Short, specific status labels and one clear primary action per page.
- Detail views that show current state, progress, history, and the next valid action together.
- Compact dialogs/forms that preserve context instead of sending users through unnecessary pages.
- Calm use of color: attention and workflow state, never decoration.

## Visual Personality

### Tone

- Quietly technical and operational, appropriate for robotics-data delivery.
- Precise, not sterile: use comfortable spacing and readable typography.
- Confident through structure and consistency, not visual decoration.
- Accessible by default: visible focus, strong contrast, readable error states, and color never as the only status signal.

### Things to Avoid

- Oversized hero headings, value-proposition copy, or marketing layouts.
- Gradient backgrounds, glassmorphism, decorative illustrations, or floating color blobs.
- A page made from nested cards.
- Excessive rounded pills and badge clutter.
- Hidden critical actions behind ambiguous icon-only controls.
- Generic dashboard widgets that do not help a client or operator complete work.
- Long instructional text embedded in the interface. Labels, empty states, and validation messages should be concise and contextual.

## Layout

### Application Shell

Desktop layout:

```text
+-------------------+----------------------------------------------------+
| Brand             | Header: page title, context, current user menu    |
| Dataset Request   +----------------------------------------------------+
| Desk              |                                                    |
|                   | Main content                                       |
| Navigation        | - page heading and primary action                  |
| - Requests        | - compact filters / summary                         |
| - Episodes        | - table, form, or detail panel                      |
| - Analytics       |                                                    |
| - Users (admin)   |                                                    |
|                   |                                                    |
| Signed-in user    |                                                    |
+-------------------+----------------------------------------------------+
```

- Persistent left sidebar on desktop, approximately 232px wide.
- Main content is a full-height work surface with a maximum readable content width, not a stack of floating cards.
- Slim top header, approximately 56px high, with page context and account controls.
- Content padding: 24px desktop, 16px tablet/mobile.
- On small screens, sidebar becomes a simple top navigation/menu and tables become horizontally scrollable or show a reduced column set.

### Page Structure

Each work page follows a stable pattern:

```text
Breadcrumb/context only when it resolves real ambiguity
Page title                         Primary action
One-sentence context only if needed
Filters / metrics strip
Main table, form, or detail workspace
```

Do not place every section inside a card. Use a page background plus dividers; reserve bordered surfaces for tables, compact summary blocks, modals, and forms requiring a clear boundary.

## Design Tokens

Use CSS custom properties so the UI remains consistent and can be changed centrally.

### Color

```css
:root {
  --canvas: #f7f8fa;
  --surface: #ffffff;
  --surface-muted: #f1f3f5;
  --border: #d9dee5;
  --border-strong: #b8c1cc;

  --text: #17212b;
  --text-muted: #5e6b78;
  --text-subtle: #74808c;

  --nav: #17212b;
  --nav-active: #263646;
  --nav-text: #dce5ed;

  --primary: #006d77;
  --primary-hover: #005b64;
  --primary-text: #ffffff;

  --success: #247a3d;
  --success-bg: #e8f5eb;
  --warning: #9a6700;
  --warning-bg: #fff4d6;
  --danger: #b42318;
  --danger-bg: #ffebe9;
  --info: #2563a5;
  --info-bg: #eaf2fb;
}
```

The palette deliberately uses deep blue-green for primary action, neutral slate for structure, and distinct green/amber/red/blue status colors. It avoids a single-hue wash while keeping the interface calm.

### Typography

- Use a system sans-serif stack: `Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif` if Inter is bundled; otherwise omit it rather than fetching it from a third party.
- Base font size: 14px or 15px; line height 1.45 to 1.5.
- Page title: 24px, semibold.
- Section heading: 16px, semibold.
- Table header and labels: 12px/13px, medium weight, normal letter spacing.
- Metadata: 13px, muted color.
- Never use negative letter spacing or viewport-based font-size scaling.

### Spacing and Shape

- Base spacing unit: 4px.
- Common gaps: 8px, 12px, 16px, 24px, 32px.
- Control height: 36px standard, 40px for prominent form actions.
- Icon button: fixed 36px square.
- Border radius: 4px for inputs/buttons/table containers, 6px maximum for modal/dialog surfaces.
- Border width: 1px, using `--border`.
- Shadows are minimal: use borders and surface contrast first; at most one subtle modal/dropdown shadow.

## Core Components

### Navigation

- Wordmark in the sidebar: `Dataset Request Desk`, with `Data operations` as small supporting text if helpful.
- Use familiar line icons only where they improve scanability; each nav item keeps a text label.
- Active item has a restrained background and a narrow left accent, not a giant colored card.
- The user menu shows name, role, and logout action.
- Admin-only navigation never replaces server-side authorization.

### Buttons

- Primary: solid teal, used once per primary page action, such as `Create request` or `Import episodes`.
- Secondary: neutral bordered, for non-destructive alternatives.
- Destructive: red text/border or solid red only in a confirmation context.
- Icon-only buttons are limited to universally recognizable, repeated actions such as close, filter reset, or refresh. They require accessible labels/tooltips.
- Disable a button while an HTMX request is in flight and show concise progress state without changing layout.

### Forms

- Labels always sit above inputs; placeholders are examples, not labels.
- Group related fields in one-column layout by default; two columns only when fields are short and naturally paired, such as deadline and episode count.
- Validation appears beneath the affected control, with a text explanation and visual signal.
- Preserve entered values after validation failure.
- Destructive decisions, such as rejecting a delivery or deactivating a user, require a compact confirmation dialog with a reason field only where business value warrants it.

### Tables

Tables are the primary operator surface.

- Sticky header when the table scrolls within a long work surface.
- Dense but readable row height: 48px to 56px.
- Left-align text; right-align counts, durations, and dates only when it aids comparison.
- Whole rows can open details; distinct inline controls must not cause accidental navigation.
- Use visible hover and keyboard focus states.
- Columns default to the information required for decisions, not every database field.
- Pagination exposes current range, total where cheap, and next/previous controls.

### Status Indicators

Status uses a compact labeled badge plus text in the surrounding row/detail area. Color is supplemental, never the only signal.

| Status | Meaning | Token |
| --- | --- | --- |
| Submitted | Needs operator pickup | info / blue |
| In progress | Operators are fulfilling it | warning / amber |
| Delivered | Waiting for client decision | primary / teal |
| Accepted | Fulfilled successfully | success / green |
| Rejected | Requires rework | danger / red |

Badges use a low-saturation background with high-contrast text. Do not use animation to signal status changes.

### Feedback States

- **Success:** brief inline confirmation or toast after an operation; updated row/detail is the primary proof.
- **Error:** clear action-oriented message near the failed control. Server errors provide a retry path and request/correlation ID if implemented.
- **Loading:** HTMX target shows a compact spinner/skeleton; unrelated page content remains usable.
- **Empty:** state the absence and show the relevant next action, e.g. `No requests yet` plus `Create request`.
- **No results:** distinguish filtered-empty from globally empty and offer `Clear filters`.
- **Permission denied:** explain that access is unavailable without revealing private data.

## Role-Based Screens

### Login

The only unauthenticated screen. It is restrained and centered, with application name, email/password fields, sign-in button, and clear inline error feedback. It is not a marketing page.

### Client Request List

The client lands on their own request list.

Columns:

- Request ID
- Task name
- Episodes requested
- Deadline
- Status
- Last updated

Primary action: `Create request`.

The table makes delivered requests visually easy to find. Their detail page presents `Accept delivery` and `Request rework` actions only for the owning client and only while status is delivered.

### Client Request Creation

Focused form with task name, requested episode count, deadline, and optional notes. Submission returns the new request in submitted status and returns the client to its detail/list state.

### Operator Request List

Operators see requests across clients. The top filter strip includes status, task name, client, and deadline horizon only if implemented without clutter.

Columns:

- Request ID
- Client
- Task
- Progress (`assigned / requested`)
- Deadline
- Status
- Updated

The initial sort should prioritize action: submitted requests and nearest deadlines before completed work. If this becomes complicated, use an explicit sort control rather than hidden magic.

### Operator Request Detail and Assignment Workspace

The request detail is a two-column desktop layout:

```text
Request context and status action     Eligible episodes
client, task, deadline, progress      task/quality filters
status history                         selectable/listed results
assigned episode list                  assign action
```

The progress count is always visible: `124 / 200 episodes assigned`. The `Mark delivered` action is disabled with an explanation until the required count is met; the server still enforces the same rule.

### Admin User Management

Compact user table with email, name, role, account status, and last action. Create/change-role/deactivate actions are explicit and use confirmations for deactivation. No client or operator UI contains admin controls.

### Analytics

Start with accessible summary tables and small basic charts only if they make trends more legible. Do not add decorative charts. Date range is prominent; the current range is visible in every result.

## HTMX Interaction Contract

- Forms use standard server endpoints and work with full-page submission as a baseline where practical.
- HTMX enhances forms, filters, table pagination, status transitions, and assignment actions with targeted HTML swaps.
- Return a focused partial for a partial request and a complete page for direct navigation.
- Ensure HTMX error responses replace or populate a dedicated error region instead of silently failing.
- Use `hx-indicator` for local loading feedback; do not block the whole page for a row-level update.
- After status/assignment actions, refresh the progress/status/detail fragments together so the page cannot display stale workflow state.

## Accessibility and Responsive Behavior

- Meet WCAG AA contrast for text and controls.
- Every input has an associated label; every icon-only control has an accessible name.
- Visible keyboard focus uses a consistent high-contrast outline.
- Native semantic elements come first: buttons, links, tables, labels, fieldsets, and dialog behavior.
- Error messages are announced with appropriate live regions when updated by HTMX.
- Tables remain usable on narrow screens through horizontal scrolling and a reduced default column set; do not shrink type to an unreadable size.
- Touch targets remain at least 36px, with extra spacing where practical on mobile.

## CSS and Asset Rules

- Write a small, purposeful CSS system using the tokens above; avoid adding a heavyweight component framework for this application.
- Use a locally installed/bundled icon library if needed; do not hand-draw unfamiliar SVG icons.
- No external image assets are necessary for this operational tool. The interface should earn clarity through typography, layout, and data presentation.
- Keep CSS organized by tokens, layout, components, and page-specific exceptions. Avoid inline style accumulation.
- Test desktop at approximately 1440px wide and mobile at approximately 390px wide before considering a screen done.

## Design Quality Checklist

- [ ] The first authenticated screen exposes useful work, not a welcome/marketing panel.
- [ ] Every role can identify its next valid action without reading a manual.
- [ ] Server validation errors appear where the user can act on them.
- [ ] Status is readable by text, not color alone.
- [ ] Tables, filters, and forms remain aligned and stable during HTMX updates.
- [ ] No text overflows, control labels wrap awkwardly, or actions shift layout when loading.
- [ ] Desktop and mobile layouts have been manually tested.
- [ ] The UI uses consistent spacing, border radius, focus states, and status treatment.
- [ ] Screens avoid decorative cards, gradients, and generic dashboard clutter.

