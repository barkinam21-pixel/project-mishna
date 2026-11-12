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

העתק טכני של ה־WAV הנגזר גובה גם ב־[Google Drive הפרטי](https://drive.google.com/file/d/1j0FbtXKA4di2CD022PXcq-HIWh-QVx_b/view?usp=drivesdk). קובץ ה־48kHz נבדק מחדש לאחר הורדה דרך החיבור המאומת: SHA-256 `86df885f38ad8dfa8759b8bf3e0be2dfd156fa4057d592e79c53628be79d6e95`, הרשאות owner בלבד ו־`shared=false`. המקור המקורי לא שונה והקובץ אינו N01 או N02.

## בקרה
[הרצת GitHub Actions](https://github.com/barkinam21-pixel/project-mishna/actions/runs/42435032581): 20 בדיקות עברו (5 preflight, 4 review board, 3 asset bridge, 8 private restoration). זו בדיקת קוד ללא חשיפה של קובצי מדיה פרטיים, ולא אימות סרט מוכן. אין תמונה חדשה, רינדור סרט, חיוב חיצוני, מיזוג או פרסום בסבב זה.

## ביקורת פורמט חדשה — תיקון נכסי ייחוס, בלי יצירת מדיה
- בבדיקת שני ארכיוני הייחוס הפרטיים נמצאו 27 תמונות שלמות, אך **25 קבצים בעלי סיומת PNG מכילים בפועל נתוני JPEG**. בפרט שישה מתוך שמונת מקורות ההנחיה הפעילים נשאו סיומת מטעה. אין להניח שסיומת הקובץ משקפת את הפורמט.
- ב־ZIP המצומצם הישן היו פיזית רק שמונה תמונות, אך הקובץ `manifest.json` שבו עדיין מנה את כל 27 התמונות. זהו **מניפסט מלא**, לא רשימת הקבצים הזמינים באותה חבילה.
- [חבילת הייחוס המתוקנת, פרטית ובבעלות המשתמש](https://drive.google.com/file/d/1HDRDMWD3539nSNa2UnvrA8aGBozlopgn/view?usp=drivesdk) מכילה שני PNG ושישה JPEG ששמם הותאם ל־`.jpg` ללא שינוי הבתים, עם מניפסט בן שמונה רשומות בלבד. ה־SHA-256 שלה: `1394a144f2731d229d0a38179aa351a1f6ff37b53c629bf18ba108481c75d3ef`. ההורדה החוזרת מ־Drive אומתה והתיקייה נשארה owner-only.
- 19 תמונות ההקשר/hold **עדיין קיימות בארכיון המלא המקורי**; הן אינן חלק ממקורות ההכוונה הפעילים ואין להעבירן למודל באופן אוטומטי.
- לא נוצרו תמונות חדשות; לא בוצע שינוי בקול, במועמדת OPN02, בזכויות או באישורי פרסום. דגלי העלאה לספק ופרסום נשארים `false`.
- בודק משולש לקריאת ארכיון המקור, החבילה הישנה והחבילה המתוקנת: `python -m tools.reference_pack_audit --full <private-full.zip> --curated <private-old.zip> --corrected <private-corrected.zip>`. ללא רשת וללא העלאת החומרים ל־GitHub.
- [דוח ביקורת ללא תמונות](evidence/private-reference-format-audit-2026-11-08.json).

## אימות אינטגרציה לאחר סגירת ההרשאה
- ניסיון יצירת OPN02 היחיד שנרשם ב־`docs/evidence/opn02-rear-wide-2026-11-08.json` **כבר נוצל**. ב־`episodes/berakhot-01-01/comfy-opening-images.json` הוגדר `generation_approved=false`; נדרש אישור חדש ומפורש לכל בקשת יצירה עתידית. `zero_cost_compute_verified=false` ו־`component_licenses_verified=false` נשארו סגורים.
- הביקורת חשפה רגרסיית בדיקות: בדיקת ה־JPEG עם `Fake CloudflareClient` הניחה שהדגל בפרודקשן פתוח. כעת הבדיקה מאפשרת יצירה **רק בעותק בזיכרון של מניפסט סינתטי**, לא במניפסט האמיתי.
- אימות CI על commit `217c85cfe7b7dedf1db4faf6a1acc35aeaeae6dd`: [בדיקות סצנה](https://github.com/barkinam21-pixel/project-mishna/actions/runs/42437428574), [400 בדיקות ומבחני מקור וקול](https://github.com/barkinam21-pixel/project-mishna/actions/runs/42437428564), [בדיקת הרכבה טכנית](https://github.com/barkinam21-pixel/project-mishna/actions/runs/42437424272) — כולם `success`. רינדור זה משתמש בנתוני ניסיון טכניים, **לא** במדיה המאושרת לסרט ואין טענה שהסרט המלא נוצר.
- השוואה חזותית של שלוש גרסאות OPN02: [לוח פרטי](https://drive.google.com/file/d/10KmzacXMeTI13Mz5Kv1dEBJky-nbO_qq/view?usp=drivesdk) ו־[דוח הערכה](evidence/opn02-three-candidate-visual-review-2026-11-08.json). 0/3 מאושרות; הדרישה לדמויות בגובה כ־30% ומראה ציורי מופיעה כבר בפרומפט המקורי ולכן לא נטען שחזרה עליה לבדה תפתור את הכשל.
- **מה עדיין חסר:** שישה שוטים נוספים וסיום תיקון OPN02, תמונות מאושרות בפועל, קריינות סצנה N01/N02, כתוביות ותזמונים, בחינת זכויות/תורה ואישור הסרט הפרטי. אין מיזוג, חיוב, יצירה חדשה או העלאת תמונות ל־GitHub.
