// <ViewTransition> ships in the React canary that Next bundles for the App
// Router, but the installed @types/react only declares it in its opt-in canary
// types. This pulls those in; without it the component is a type error even
// though it resolves and runs fine.
/// <reference types="react/canary" />
