<!-- Cumulative changelog — NEWEST version section on top; keep the old ones. -->
<!-- HOW IT WORKS: when main is pushed with a new version in desktop/package.json, -->
<!-- the release workflow ships ONLY the section whose heading matches that version -->
<!-- (e.g. "## v2.2.0") as the release body / in-app "What's new". No matching -->
<!-- section = auto-generated notes are used instead, so stale notes can't ship. -->
<!-- Release prep = bump desktop/package.json + add a new section here, one commit. -->
<!-- Plain lines and "- " bullets render best in-app. -->

## v2.2.0

Game night, upgraded:

- ★ Bonus tiles — mark any tile as a secret Daily Double: it opens with a reveal splash and the host sets the wager
- Sound effects — tile picks, correct dings, wrong buzzes, and a podium fanfare (press M to mute)
- Finish game — podium finale with confetti and final standings, plus one-click play-again
- The editor flags questions that are missing answers, and warns before you start playing
- Undo and redo in the editor (Ctrl+Z / Ctrl+Y)
- Duplicate as Double — instant round two with doubled values, scores carried over
- Tidy media in Settings — clean up uploads no board uses anymore
- About now shows the full version history, not just the latest notes

## v2.1.0

Chaewon Jeopardy is back — rebuilt from the ground up. Same game you know, brand-new engine underneath:

- Board library — build and keep as many boards as you want, with autosave while you edit (no more Save dialogs)
- Your old boards still work: legacy .json saves import directly
- Build slides with any mix of images, GIFs, video, and audio — up to 4 per slide
- Stacked audio plays layered tracks in perfect sync, instantly
- Scores, used cells, and game state survive closing the app mid-game — pick up right where you left off
- Host tools: click a score to fix it, undo any award, full scoring history
- Present mode (P) for the TV, clue timer (T), and hotkeys everywhere — press ? to see them
- Second screen over wifi: turn it on in Settings and open the board on a TV or phone browser
- Share boards as .jeopardy files — double-click one to import it
- Real install wizard — pick where it goes (or keep the sensible default), no admin needed
- Start Menu and desktop shortcuts, plus a clean uninstaller that keeps your boards safe
- Updates install themselves from here on out
