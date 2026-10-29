# Native DPI capture evidence

These captures use the Windows Qt platform plugin and a real shown `MainWindow` (`window.grab()`), not the offscreen Qt platform. The host display's baseline Qt device pixel ratio is 1.25. `QT_SCALE_FACTOR` was set to 0.8, 1.2, and 1.6 to produce effective ratios of 1.0, 1.5, and 2.0 respectively. Captures were made after the timeline and inspector were placed in separate tabs so both remain usable when the available logical width is reduced.

| Effective Qt scale | Capture |
| --- | --- |
| 100% | [ui-effective-100.png](ui-effective-100.png) |
| 150% | [ui-effective-150.png](ui-effective-150.png) |
| 200% | [ui-effective-200.png](ui-effective-200.png) |

At 200%, the Controls panel and Timeline tab fit in the native window; the Inspector is available on its adjacent tab and can be vertically scrolled. These are UI-layout captures only and do not claim MIDI playback or audible output.
