# שחזור פרטיות ובדיקת תמונת OPN02 — 8.11.2026

## מצב מאומת
- החבילה הפרטית נשמרה ב־Google Drive, ללא שיתוף ציבורי: [OPN02 private ZIP](https://drive.google.com/file/d/1m4OPke-0eAuNzhcxKijwsDKCk8qScftL/view?usp=drivesdk).
- SHA-256 של ה־ZIP: `370d9da290c0204b94ba72a0d4e7a5873abc9b75a44599fca2421ee111ebf0a2`.
- SHA-256 של התמונה: `e144d087fd438892725e5409096b51cf5cc1f3b82010b9a8f44acd2dbde92552`.
- **OPN02 נשארת CANDIDATE, accepted=false**. היא צריכה תיקון גודל דמויות וסגנון. אף תוכן לא אושר אוטומטית.
- צילומי המקור, לוחות ההנחיה וקטעי הקול נשארים באחסון הפרטי. אין להעלות את ה־ZIP ל־GitHub.

## תהליך שחזור יחיד בסביבה מורשית
לאחר שהקובץ הפרטי זמין למפיק בסביבה מורשית, מתוך שורש המאגר:

```bash
python -m tools.private_scene_review /private/path/to/Mishnah-OPN02-unapproved-candidate-bundle-2026-11-08.zip
```

אותה פקודה מאמתת את ה־ZIP, שחוזרת את התמונה ואת מניפסט המועמד בלבד, מפעילה את ה־preflight ויוצרת לוח בקרה תחת `private-media/scene-review/scene-contact-sheet.png`. היא **אינה** מתחברת ל־Drive בעצמה: הורדת הקובץ חייבת להתבצע דרך חיבור מורשה, ללא סוד ששמור ב־GitHub Actions. המנגנון חוסם hash שגוי, symlink, מסלול חורג, מטא־דאטה מזויפת, תמונה פגומה ודריסת קובץ פרטי אחר.

## תוצאה ואי־הבנות שיש למנוע
- כלי ה־review מנצל רק נכסים קיימים שנבדקו לפי hash; אין יצירת תמונות חדשות או חיוב ספק.
- התאמת hash אינה מעידה על אישור אמנותי, זכויות, ביקורת תורה, נוסח או פרסום.
- אין להעלות את לוח הביקורת או את קובצי `private-media` כ־GitHub Actions artifacts.
- כלי `tools.introduction_proof` נשאר שער הסמכות לקראת רינדור פרטי; כרגע הוא חסום משום שאין שבעה איורים, N01/N02, כתוביות ותזמונים מאושרים.
- בהיעדר חיבור קבוע ומורשה של אחסון פרטי לסביבת ההפקה, אין לטעון להפקה אוטונומית מרחוק.

## בסיס הקריינות הקיים
המקור המאושר לניסיון רציפות Alnilam v2 נשמר ב־[Drive הפרטי](https://drive.google.com/file/d/1ZniX8Len9_NRCJwemNdiuXdnhmKYJffz/view). ב־8.11.2026 הורד ונבדק: WAV PCM16 מונו, 24kHz, משך 49.250958 שניות, SHA-256 `f6648459ead4913e960eda94204af0c9e9e820f855a6d854b4ac3847aa7ac45d`.

בוצעה **המרת תדירות דגימה בלבד** בקובץ נפרד 48kHz PCM16 מונו, בלי ליצור קול חדש או להחליף את המקור. SHA-256 נגזר: `86df885f38ad8dfa8759b8bf3e0be2dfd156fa4057d592e79c53628be79d6e95`, 2,364,046 דגימות. הפקודה לשחזור:

```bash
ffmpeg -nostdin -hide_banner -loglevel error -i approved-original.wav -map 0:a:0 -vn -af aresample=resampler=soxr:precision=28 -ar 48000 -ac 1 -c:a pcm_s16le alnilam-continuous-v2-48khz-derived.wav
```

**אזהרת תוכן:** זהו קובץ ניסוי רציפות הקריין, לא קריינות N01/N02 התואמת לתסריט המאושר. אסור לשתול אותו במניפסט הסרט או להתייחס אליו כאל קריינות חדשה שאושרה.

## בקרה
[הרצת GitHub Actions](https://github.com/barkinam21-pixel/project-mishna/actions/runs/42435032581): 20 בדיקות עברו (5 preflight, 4 review board, 3 asset bridge, 8 private restoration). זו בדיקת קוד ללא חשיפה של קובצי מדיה פרטיים, ולא אימות סרט מוכן. אין תמונה חדשה, רינדור סרט, חיוב חיצוני, מיזוג או פרסום בסבב זה.
