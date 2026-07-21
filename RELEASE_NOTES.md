<!-- Cumulative changelog - NEWEST version section on top; keep the old ones. -->
<!-- Each release section starts with a line containing only "##", a space, and -->
<!-- the version with a leading v - nothing else on that line, ever. Do NOT put -->
<!-- that pattern anywhere else in this file (including these comments): the -->
<!-- release workflow and the in-app parser both treat it as a section start. -->
<!-- The workflow ships ONLY the section matching desktop/package.json's version -->
<!-- as the release body / in-app "What's new", and FAILS the release if that -->
<!-- section is missing - notes can't be stale or forgotten. -->
<!-- Release prep = bump desktop/package.json + add a new section here, one commit. -->
<!-- Plain lines and "- " bullets render best in-app. -->

## v2.2.2

Updates, but make them smooth:

- Hitting Restart on an update now installs silently and relaunches the app — no more setup wizard mid-update (it still greets first-time installs)
- Checking for updates while a new version is still being published now says exactly that, instead of a wall of error text
- Fixed "What's new" and Version history showing the wrong notes after an update
- The installer clears lingering background processes before updating, so updates stay reliable even from much older versions

## v2.2.1

- Fixes the app failing to start after an update on some machines ("spawn UNKNOWN") — updates now install reliably
- If anything does go wrong, the app now explains what happened and keeps a log to help us fix it

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
