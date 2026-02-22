# App Vision

> ADHD Calendar — a visual time-blocking calendar designed for ADHD coaches and their clients.

---

## Overview

A mobile-first calendar app that displays a week view of time blocks, color-coded by category. Designed to help people with ADHD visualize their schedule structure at a glance.

**Target users**: ADHD coaches and their clients

**Core value proposition**: Simple, visual weekly overview that reduces cognitive load by showing blocks as colored categories instead of dense text schedules.

---

## Key Screens / Areas

| Screen | Purpose | Priority |
|--------|---------|----------|
| Week View | Display 7-day grid of color-coded time blocks | Core |
| Block Detail | Tap a block to see full details | Core |
| Add/Edit Block | Create or modify a time block | Core |
| Coach Client Switcher | Coach toggles between client calendars | Secondary |

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | React 18 + TypeScript |
| Styling | Tailwind CSS |
| Build Tool | Vite |
| Testing | Vitest + React Testing Library |
| State | Props + local state (no global store yet) |

---

## Design Principles

1. Mobile-first — designed for phone screens, responsive up
2. Minimal cognitive load — color-coded blocks, not walls of text
3. Glanceable — a week's structure visible without scrolling

---

## Out of Scope (for now)

- Backend / API / database
- Authentication
- Push notifications
- Native mobile apps
- Multi-tenancy

---

_This file is created by `/vision` or `/clone-app` and serves as the north star for `/build-next` decisions._
_Update with `/vision --update` to reflect what's been built and learned._
