# צנרת תמונה מונחית־הפניה ל־SH09 (כלי בלבד)

מסמך עזר, לא לוח סטטוס. המצב הרשמי נשאר ב־[README](../README.md) ו־`trials.json`.

## מה קיים
`python tools/reference_guided.py` — שלבים: `plan`, `preflight`, `generate-one`, `evaluate`, `export`, או `all` (ברירת מחדל: **ריצה יבשה לא־מקוונת**, בלי רשת/GPU/משקלים/עלות).

- `plan`: אילוצי סצנה טיפוסיים (שתי דמויות, לילה, בית אבן צנוע, דלת משמאל, מנורת ענבר), מפת פריסה דטרמיניסטית (`layout-map.png`, קלט תנאי שנוצר בקוד — **לא איור**), גיבוב SHA-256 של הפניות פרטיות.
- `preflight`: קבצים, הרשאת הוצאה = 0, רישיון מתועד, מגבלת ניסיון אחד, נעילת ניסיון קודם, זמינות torch/diffusers/transformers. VRAM, מכסת Colab ושימוש נותר: `unknown`.
- `generate-one`: נחסם בלי `--allow-generate` ובלי מחסנית GPU. ניסיון אחד בלבד; `attempt.lock` מונע ניסיון חוזר (גם אחרי כישלון). לא מסמן אישור.
- `evaluate`: מדדים **ייעוצים** (גודל, בהירות לילה, ניגודיות). ספירת דמויות, אדריכלות והתמקדות = `unknown_requires_human_review`.
- `export`: ZIP פרטי עם PNG, `metadata.json` (seed, SHA, מודל, משך, חיוב `unknown`) ודוח ייעוצי; `accepted=false` תמיד.

פלט ב־`private-media/reference-guided/SH09/` (מתעלם ב־git).

## בחירת Backend
SDXL base + ControlNet canny (`diffusers/controlnet-canny-sdxl-1.0`, Apache-2.0 לפי כרטיס המודל — לאמת) לפי מפת הפריסה, עם IP-Adapter אופציונלי כשיש תמונת הפניה. דורש בערך ≥12GB VRAM; T4 חינמי של Colab כשזמין, ללא הבטחת מכסה. Inpainting נדחה (דורש תמונת בסיס). תמונות Copilot זמינות רק בצ׳אט/IDE ללא API — ספק ידני, לא נבנה מתאם. Copilot Pro הוא לקוד ולא ל־GPU/תמונות בלתי מוגבלים.

## זרימת משתמש
אפס פעולות לבדיקה לא־מקוונת (CI). ליצירה אמיתית: פעולה אחת — להריץ בסביבת GPU מותרת `python tools/reference_guided.py generate-one --allow-generate`. אין אחריות להרצת Colab ללא השגחה; אם אין GPU חינמי — המשך חסום, ללא רכישה.

## לא הוכח
אין תמונה אמיתית. הצלחה חזותית (שני גברים, בית אבן בלילה, מנורה) נבדקת רק בצפייה אנושית בפלט GPU אמיתי. לא TinyFish, לא ChatGPT images. אצוות ורכבה רק אחרי SH09 אמיתי שאושר על ידי בר.
