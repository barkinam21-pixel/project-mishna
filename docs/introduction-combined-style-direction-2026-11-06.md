# Visual style lock candidate — merged reference approved by Bar (2026-11-06)

Bar supplied five still-image references and two videos and requested a combination. A new combined illustration was generated in the conversation; Bar responded **"נהדר"**. This approves the **direction** as a style reference, not every downstream asset, not historical authenticity, and not publication.

## Expected source identity supplied by Bar — not yet verified

- Filename: `a_cinematic_detailed_illustration_in_the_same_rea.png`.
- Expected SHA-256: `e1391de34693cf897898a264662e6f4249bfa2f0a7b648c72fad49906da248f3`.
- Expected original dimensions:1672×941. Preserve those exact original bytes; do not stretch/re-encode or substitute the1280-wide chat preview to obtain a matching file.
- The four-shot board is a separate direction reference. No expected hash was supplied; compute it from accessible original bytes and record it separately. Do not pass the collage to the generator by default.
- Both images have been visually inspected in the conversation; neither original file has been verified or privately copied in this execution. Their model/seed remain unknown.

## Reference identity
- Chat-generated combined image: `/mnt/data/a_cinematic_detailed_illustration_in_the_same_rea.png` **is a conversation-local path, not a repository asset**. Do not assume it is available to GitHub Actions. Its model/seed are unknown. Before automated use, obtain a durable user-authorized copy with provenance and SHA256; do not fabricate a repo URL or hash.
- The five supplied stills and two videos are visual references only; their rights/provenance for public reuse have not been independently established. Do not automatically embed source imagery in released film.
- Previous OPN02 brief had two travelers on an empty pre-dawn path. The approved *combined* reference instead depicts two adult travelers near a stone hillside village at sunset, with an older gray-bearded man in layered dark blue and a younger brown-shawled bearded man, warm window light, olive branches and animals. **This is a creative visual-direction change**: reconcile the shot map and historicity gate before generating OPN01–07. Do not silently describe the new frame as the old dawn wilderness.

## Visual bible — candidate lock
- **Characters:** older traveler, weathered face and gray beard, tan wrapped headcloth, dark indigo outer robe over beige tunic, plain travel satchel; younger adult, dark beard and hair, brown head wrap and shawl over beige tunic, shoulder bag. The same facial structures, garments, accessories, relative heights and camera axis across all original shots.
- **Environment:** dusty path by a generic stone hillside village, warm light in stone arches, olive branches, distant livestock and rolling hills. Sunset palette of muted ochre, bronze, slate-blue and violet. This is **symbolic dramatization**; architecture, costumes and townscape are not verified reconstructions of a specific century, location or documented event.
- **Style:** hand-painted cinematic semi-realism, readable depth, restrained expressions, textured cloth/stone, rich but not glossy, adult dramatic atmosphere. Avoid childlike expressions, oversized eyes, glossy 3D, photorealistic portrait inserts, garish saturation, fake Hebrew glyphs and excessive fantasy effects.
- **Continuity:** all seven OPN frames must be *independent original compositions*, not crops of the approved master. Same character sheets and light direction; map left/right and eyelines explicitly before generation. No image should invent a conversation as documented history.
- **Camera plan:** OPN01 boots on path; OPN02 master with two adults and village; OPN03 younger traveler looking to older; OPN04 reverse/OTS older listening; OPN05 younger's subtle reaction; OPN06 restrained hand gesture; OPN07 new wide as they continue toward the village. Cut reasons follow narration, not arbitrary zooms.
- **Voice:** preserve previously accepted Alnilam continuity take and profile. Reject later childish retake; do not perform further voice tests.
- **Cost:** ChatGPT image generation may consume plan usage; exact quota unknown. No fal.ai account assumed, no new payments authorized.

## Next executable production gates
1. Preserve a durable, hash-verified copy of the combined reference in the private asset store; record license/provenance and approval status.
2. Generate a text-only continuity sheet and top-down blocking/eyeline plan from this frame; reconcile dawn vs sunset with Bar's approval (the combined frame is sunset).
3. Draft original composition prompts for remaining six OPN shots, all referencing the same approved character sheet, but **do not claim reference conditioning works without testing**.
4. Run current introduction validator/dry-run; report missing real media accurately. The seven-second synthetic MP4 is technical proof, not artistic proof.
5. Produce a 60–90-second private artistic proof only when 7 licensed images, matching Alnilam narration, subtitles and timings exist and have passed review. No publication, PR merge, new paid service or silent billing.

**Approval state:** combined style direction liked by Bar; film assets pending. 


## Visual Bible — implementation revision 7.11.2026

**בסיס:** שתי התמונות המוצגות בשיחה והוראת בר המאוחדת. הניתוח החזותי להלן נעשה מתצוגת השיחה. הוא אינו אימות של קובצי המקור: PNG המקור והלוח אינם נגישים כרגע כבתים, ולא חושבו להם hash או מידות בפועל. ה־hash והמידות שסיפק בר הם ערכים צפויים, לא תוצאת בדיקה. הכיוון מאושר; זהות מדויקת ברמת פרטי הפנים תינעל כנכס ממוחשב רק לאחר אימות הקובץ.

### Character Bible

| מזהה | זהות והופעה מחייבת | רציפות וביקורת |
|---|---|---|
| A · הנוסע המבוגר | גבר מבוגר, זקן אפור מלא, פנים חרושות קווים והבעה מהורהרת; כיסוי ראש בגוון חול, גלימת אינדיגו כהה מעל טוניקה בהירה ותיק מסע פשוט. | אין לתת לו פנים חדשות, להצעירו, להקצין זקנה או להוסיף סמל. מבנה אף/לחיים/גבות, קו הזקן, קפלי הכיסוי, הגובה היחסי ומסלול הרצועה ייבדקו מול המקור המאומת. |
| B · הנוסע הצעיר | גבר בוגר בעל שיער וזקן כהים, כיסוי ראש ושכבות בגוני חום, טוניקה בהירה ותיק; סקרנות רצינית ולא פליאה ילדותית. | אינו ילד/נער. לשמור על אותו קו לסת, זקן, שיער, כתפיים, קפלי בגד ורצועות; אין להחליף גיל, מבטא חזותי או פרופורציות בין שוטים. |

אין שמות, זהות של תנא או ביוגרפיה מדומה. הייחוס המשולב ישמש לשתי הדמויות, בלי לייצר דפי דמות חדשים ובלי לדרוש אותם כתנאי מלאכותי לפני ניסיון OPN02. צד הנשיאה האנטומי המדויק ופרטים זעירים שלא נראים בבירור לא יומצאו מן התצוגה המוקטנת; המקור המאומת יהיה הסמכות.

### Environment Bible ו־Color Script

- כפר אבן אנונימי על צלע הר, דרך מאובקת מתפתלת, גבעות, זיתים וצמחייה ים־תיכונית. אין לזהות אתר, מאה או שיטת בנייה כאמת היסטורית ללא מקור. הקשתות, המבנים והבגדים הם בחירות אמנותיות בהמחזה סמלית.
- חזית: ענפי זית/דרך ואבן במינון שאינו מסתיר פנים; אמצע: שני הנוסעים; רקע: שכבות כפר וגבעות. עומק נוצר מגודל, חפיפה וניגודיות אטמוספרית, לא מטשטוש קיצוני שמבטל את הציוריות.
- פתיחה OPN01–02: אדמה ואוכרה, שולי אור זהובים, אינדיגו בבגד ובצל. OPN03–05: אותה שעה ואותו אור, עם הפרדה מקומית של הפנים מן הרקע. OPN06: חום בד ועור, אור טבעי רך. OPN07: הרחבת הכחול־סגול בנוף בלי להפוך ללילה.
- הפלטה היא הוראת אמנות, לא מדידת צבע מן PNG המקור: אוכרה/ברונזה, זהב מאופק, אינדיגו וסגול מעושן. טקסטורות בד ואבן מצוירות, לא עור פוטוריאליסטי, פלסטיק או 3D מבריק.
- אור מפתח: שמש שקיעה משמאל ומאחור, אור שמיים קר ורך בצל; חלונות חמים חלשים משניים. אין להזיז את השמש לצד אחר בקלוז־אפ או להפוך חלון למקור key בלתי מוסבר.
- לילה/אש: מחקר הבימוי D שומר מסה כחולה כהה סביב אור אש חם ומקומי. הוא מיועד לרצף לילי נפרד בעתיד, ולא קפיצת זמן בתוך שבעת שוטי הפתיחה.

### מפת העמדה וציר

תרשים עליון סמלי: הדרך היא ציר X, כיוון המסע +X; A ב־(0,0), B ב־(1,0), מצלמת בסיס ב־(0.5,-4), הכפר במרחק לכיוון +X, מקור האור ב־(-3,+3). כל מצלמות הפתיחה נשארות בצד Y השלילי. אין כאן קואורדינטות של אתר אמיתי.

בפריים הבסיס A משמאל ו־B מימין. B מחפש את מבט A שמאלה; A מקשיב לכיוון ימין. ל־OPN04 ניתן לשים את כתף B בימין הקדמי ו־A משמאל ברקע: זהו שוט הקשבה של המבוגר, ולא חזרה על שוט מעבר כתף המבוגר אל הצעיר. שוט אחורי אינו היתר אוטומטי להפוך את הציר. שינוי גובה מצלמה מותר כאשר הוא מסביר מקום או קשב, בלי להזיז את השמש או להחליף צדדים.

### ניתוח לוח A–D — השראת בימוי, לא חומרי הסרט

| לוח | מה נלמד | שימוש מקורי מתוכנן |
|---|---|---|
| A · דיוקן המבוגר | פנים בעלות משקל, מבט מהורהר, סמכות ללא פאתוס; הפרדת אור חם מן נוף צללי. | שוט הקשבה בגובה העיניים, מבט וחלל נשימה לכיוון הצעיר. לא לחתוך את אזור A מן הלוח ולכנותו איור חדש. |
| B · שני הנוסעים | יחס אנושי בין מבטים, ידיים ומטען; קומפוזיציה המסבירה קשר בלי דיאלוג. | master חדש של OPN02 עם אותה זהות ולבוש, עומק ותחושת תנועה מקוריים. |
| C · המסע | אנשים קטנים מול דרך וגאוגרפיה, שכבות מרחק ותחושת המשך. | רחב חדש ל־OPN07. הזווית האחורית והמיקומים בלוח אינם מחייבים החלפת צדדים ביחס ל־master; יש לשמר את הציר שננעל. |
| D · המדורה | אור אש קרוב, אזור חשוך בעל תפקיד, הקשבה ושתיקה במקום מלודרמה. | מילון בימוי לסצנה לילית נפרדת בעתיד, עם מעבר זמן מתוכנן. לא להכניס מדורה לפתיחה רק כדי לחקות את הלוח. |

השפעת קורה/אווטאר נשארת ברמת קנה מידה, מעברי רחב–אינטימי, שינויי גובה וקצב רגשי. אין העתקת דמויות, עיצובים, פריימים, מנגינות או קול מדבב.

### מצב הפקה ושער ראשון

שבעת השוטים מפורטים במניפסט הקיים ובמפרט האיורים המעודכן. OPN02 בלבד מורשה כניסיון אחד, בכפוף למקור המאומת, מסלול ללא חיוב והתאמת הספק. אף איור לא נוצר בסבב זה. אין תזמון מדוד, קריינות פתיחה תואמת או מוזיקה חדשה. Alnilam רציפות v2 נשמר ללא שינוי.
