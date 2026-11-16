# The app

| File | What it is |
|---|---|
| `main.tsx` | Mounts the app |
| `App.tsx` | State, data loading, the event handling of a question, and the top bar |
| `Stage.tsx` | The stage: the file shelf, the 3D floor, the huddle log |
| `Floor3D.tsx` | The 3D floor (three.js): the bucket of files, the translators around it, the orchestrator, the verifier, and the story line over them |
| `story.ts` | Who is working and what is happening, worked out from each event of a question; drawn by the 3D floor |
| `Floor2D.tsx` | The flat floor, shown when the browser has no WebGL |
| `Chat.tsx` | The chat: messages, citation markers, the "Could not be verified" block, the input |
| `Panels.tsx` | Drawers and cards: files, agents, sessions, context map, citation, file card, agent card |
| `styles.css` | All styles, light and dark |
| `backend/` | The `Backend` interface and its implementations |
| `demo/` | The scripted demo and its test |
