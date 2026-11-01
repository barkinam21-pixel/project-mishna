# צנרת תמונה מונחית־הפניה ל־SH09 (כלי בלבד)

מסמך עזר, לא לוח סטטוס. המצב הרשמי נשאר ב־[README](../README.md) ו־`trials.json`.

## מה קיים
`python tools/reference_guided.py` — שלבים: `plan`, `preflight`, `generate-one`, `evaluate`, `export`, או `all` (ברירת מחדל: **ריצה לא־מקוונת**, חסומה בלי `--allow-generate`; בלי רשת/עלות).

- **מצב אמיתי היחיד:** תמונה־לתמונה (`StableDiffusionXLControlNetImg2ImgPipeline`). תמונת `--reference` פרטית היא מקור ה־img2img, קווי Canny נגזרים ממנה (`control_image`), עוצמה נמוכה 0.3. אין נפילה שקטה ל־SDXL טקסט בלבד: בלי `--reference` יצירה אמיתית **חסומה** ולא נצרכת נעילת ניסיון. התמונה לא מועלית ל־git (רק SHA-256 ושם קובץ). תמונת ההפניה של המשתמש אינה במאגר.
- `preflight`: פרומפט/הוצאה=0/רישיון/ניסיון יחיד/נעילה קודמת, ובנוסף `torch.cuda.is_available()`, VRAM כולל (≥12GB), Pillow, opencv, accelerate, ושגרסת diffusers המותקנת כוללת את צינור ControlNet Img2Img. CPU בלבד נחסם. מכסה נותרת: `unknown`.
- `generate-one`: ניסיון אחד; `attempt.lock` נלקח רק אחרי שה־preflight עבר, ונשאר גם אחרי כישלון.
- `all --reference X --allow-generate`: ניסיון אחד ואז אוטומטית `evaluate` + `export` (ZIP עם PNG, `metadata.json` ו־SHA-256). אין שלבים נוספים.
- `evaluate`: ייעוצי בלבד (גודל, בהירות, ניגודיות); דמויות/אדריכלות/מיקוד = `unknown_requires_human_review`.
- `export`: `accepted=false` תמיד. תוצר mock מסומן `synthetic_mock=true`.

פלט ב־`private-media/reference-guided/SH09/` (מתעלם ב־git). IP-Adapter אינו מופעל (תאימות לא נבדקה).

## בחירת Backend
SDXL base + ControlNet canny (`diffusers/controlnet-canny-sdxl-1.0`, openrail++ לפי [כרטיס המודל ב־Hugging Face](https://huggingface.co/diffusers/controlnet-canny-sdxl-1.0) — יש לבדוק תנאי שימוש לפני הפצה). בדיקת סף שמרנית של ≥12GB VRAM (לא הבטחת הצלחת הרצה); משתמש ב־`enable_model_cpu_offload()` להפחתת צריכת זיכרון על T4, בהתאם ל[הנחיות Diffusers](https://huggingface.co/docs/diffusers/main/using-diffusers/sdxl). T4 חינמי של Colab כשזמין, ללא הבטחת מכסה. תמונות Copilot זמינות רק בצ׳אט/IDE ללא API — ספק ידני. Copilot Pro הוא לקוד ולא ל־GPU.

## זרימת משתמש
בדיקה לא־מקוונת: אפס פעולות (CI). יצירה אמיתית: העלאת תמונת הפניה פרטית לסביבת GPU מותרת והרצת פקודה אחת: `python tools/reference_guided.py all --reference <path> --allow-generate`. אין אחריות להרצת Colab ללא השגחה; אם אין GPU חינמי — חסום, ללא רכישה.

## לא הוכח
אין תמונה אמיתית. הצלחה חזותית (שני גברים, בית אבן בלילה, מנורה) נבדקת רק בצפייה אנושית בפלט GPU אמיתי. לא TinyFish, לא ChatGPT images. אצוות ורכבה רק אחרי SH09 אמיתי שאושר על ידי בר.
