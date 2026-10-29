# Add a manual browser session mode

When developers need to inspect locally forwarded frontend or backend changes by hand, `ydf-browser run` without `--dsl` SHALL provide a separate manual browser session: perform the existing API login with environment credentials, open the resolved `base_url` root in a visible browser, keep request forwarding active, and let the user control page interactions and closure. The mode SHALL NOT fabricate a DSL test suite or execution report; a successful visible startup followed by user/browser closure is a normal exit, while startup failures remain non-zero.

## Considered Options

- Treat the invocation as an empty DSL test suite: rejected because it would misrepresent manual work as automated verification and produce misleading reports.
- Add a separate subcommand: rejected because it would duplicate the existing login, profile, browser, and request-forwarding lifecycle.

## Consequences

- `--headless` is incompatible with this mode because the user must interact with a visible browser.
- The default persistent profile and `--no-persistent-profile` remain shared with ordinary real runs.
- Browser closure becomes the completion signal; `Ctrl-C` remains an explicit user interruption path.
- Environment-level credentials are used; tenant, default organization, and fiscal year are left for the user's manual UI actions.
- Any page opened in the same browser context remains part of the session, including user-created tabs.
- The mode is selected only when both `--dsl` and `--dsl-list` are absent. An empty or invalid DSL list remains a DSL input error.
- DSL filters, fixture inputs, report paths, performance collection, and AI observation options are rejected without DSL input.
- A normal close returns the minimal `manual_browser_session/browser_closed` result; startup failures use the existing non-zero error path and no manual-session report is written.
- Forwarding is optional and remains active for all pages in the context, but manual-session forwarding events are not persisted as a new artifact format.
