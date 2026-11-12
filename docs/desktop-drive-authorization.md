# חיבור Drive פרטי — המשך ההגדרה הקיימת

הכלי הקיים `tools/authorize_private_drive.py` עודכן לבחירת שלושת הקבצים באמצעות **Google Picker המובנה באישור Desktop OAuth**. אין צורך להחליף את לקוח ה־Desktop, להקים ממשק JavaScript, ליצור API key או להתקין ספריות Python. Python ו־GitHub CLI שכבר הותקנו נשארים בשימוש.

## מה השתנה

הכלי מבקש **רק** `https://www.googleapis.com/auth/drive.file`, מוסיף `trigger_onepick=true`, `prompt=consent`, `allow_multiple=true` ומסנן את הבחירה לשלושת המזהים הקיימים באמצעות `file_ids`. החזרה מ־Google חייבת לכלול את שלושתם בדיוק ב־`picked_file_ids`; בחירה חלקית, כפולה או זרה חוסמת שמירת סוד. מזהים אינם הרשאה: Google עדיין מחייב אישור ובחירה אישיים.

מסלול `--existing-files` הישן **נחסם לפני כל כניסה או רשת**. אין להריץ את הפקודה הישנה שמבקשת גישה מלאה. הרשאה מצומצמת אינה מנגנון שמגביל את האפליקציה לשלושה קבצים לעד: היא חלה על קבצים שנבחרו/נפתחו עבור האפליקציה או נוצרו על ידה. הכלי הנוכחי דורש את שלושת הקבצים המדויקים, בלי שינוי ACL ובלי יצירת קבצים.

## מה נותר ב־Google Cloud

אין ליצור מחדש פרויקט, OAuth Client, קובץ JSON, חשבון GitHub או את שלושת הקבצים.

1. באותו פרויקט `Mishnah Private Drive`, ודא ש־**Google Picker API** מופעל בנוסף ל־Drive API שכבר הופעל. [עמוד Google Picker API](https://console.cloud.google.com/apis/library/picker.googleapis.com). לפי התיעוד זה תנאי למסלול; לא אומת בחשבון בפועל.
2. ב־Data Access, ההרשאה הנדרשת למסלול זה היא `drive.file` בלבד. הקוד אינו מבקש Drive מלא או הרשאות זהות/Gmail/Cloud. בדוק שההרשאות במסך Google תואמות לכך; אין לאשר בקשה רחבה.
3. לצורך חיבור יציב, יש לפתור את חסימת Branding ולהגיע ל־**In production לפני האישור הסופי**. Google דורש קישורי דף בית, מדיניות פרטיות ותנאי שימוש עבור External Production, ודף בית בדומיין מאומת שבבעלותך. אין להמציא כתובות או להניח שזמן המתנה יתקן שדות חסרים. `drive.file` מסווג non-sensitive, אך זה אינו מבטל את דרישות ה־Branding או מבטיח אישור Google.

**Testing אינו חיבור קבוע:** refresh token של הרשאת Drive במצב External/Testing פג לאחר שבעה ימים. אחרי מעבר ל־Production יש לבצע אישור חדש; אין להסיק שמצב הפרויקט שינה את ה־token הישן. גם Production אינו מבטיח הרשאה נצחית: ביטול הסכמה, מדיניות ארגונית, חוסר שימוש ומגבלות tokens עלולים לבטלה.

ב־13.11.2026 הדפדפן של Work החזיר `Site Unavailable` עבור Google Cloud. לא בוצעה כניסה לחשבון, לא נבדקו/שונו הגדרות Picker/Branding/Production, ולא אושר OAuth חי. אין לבלבל מגבלת גישה זו עם תקלה בהגדרות החשבון או חסימת בוטים מוכחת.

## ההפעלה ב־Windows

לאחר פתרון ההגדרות, השתמש **בגרסה המעודכנת בענף PR #53**, ולא בעותק הישן שכבר הורד. אין להתקין Python/gh שוב ואין להוריד JSON חדש. מתוך התיקייה שבה נמצא הכלי המעודכן:

```powershell
py authorize_private_drive.py
```

הכלי מאתר אוטומטית קובץ Desktop תקין יחיד בשם `client_secret*.json` בתוך Downloads. אם אין בדיוק קובץ אחד מתאים, הוא עוצר בלי לנחש; אפשר לציין את הקובץ שכבר קיים:

```powershell
py authorize_private_drive.py "$env:USERPROFILE\Downloads\client_secret.json"
```

בדפדפן שייפתח בחר את חשבון הבעלים ואת **שלושת הקבצים** המוצגים, ואשר גישה רק לקבצים שנבחרו. סודות וקובץ הלקוח אינם מועתקים לצ׳אט. אל תפעיל הקלטת מסך/PowerShell Transcript בזמן האישור.

לאחר האישור הכלי מחליף code באמצעות PKCE, בודק שההרשאה שהוחזרה היא בדיוק `drive.file`, מבצע refresh אמיתי, ובודק באמצעות ה־access token המחודש שכל קובץ הוא בבעלות החשבון (`ownedByMe`), פרטי (`shared=false`, הרשאת בעלים אחת) וניתן לעריכה. רק אז הוא מעביר את `MISHNAH_DRIVE_OAUTH_JSON` ל־GitHub CLI ב־stdin. הסוד אינו נכתב לקובץ או מודפס. כשל לפני השמירה אינו מחליף סוד קיים. כשל/timeout בשמירת GitHub אינו מוכיח אם השרת כבר שמר את הסוד; אין ניסיון חוזר אוטומטי ואין הודעת הצלחה.

## בדיקת Actions אחרי האישור

שמירת הסוד אינה הוכחה שהמערכת העצמאית עובדת. יש להפעיל את ה־workflow הקיים **במצב `check` בלבד**, על הגרסה המעודכנת, ולראות הצלחה מפורשת של `drive-readonly` עם `DRIVE_RESTORE_AND_LOCAL_PREFLIGHT_VERIFIED`. מצב זה אינו משנה קבצי Drive ואינו מפעיל מודל. `run`, יצירה, ה־SHA המאושר ושערי התקציב/הפרטיות נשארים מחוץ למשימה הזו. אין צורך למזג PR כדי לאשר OAuth; זמינות dispatch לענף נקבעת לפי ה־workflow הקיים ב־GitHub.

## אבטחה ואימות

- PKCE-S256 ו־state אקראי; HTTP callback על `127.0.0.1` בלבד, Host מדויק, דחיית query כפול/נתיב אחר/state שגוי; timeout חמש דקות וחיבור מקומי חסום בזמן לאחר שתי שניות של אי־פעילות.
- ביטול מחזיר חסם מיד, בלי לחכות חמש דקות. תשובת הדפדפן אינה מכריזה שהסוד נשמר.
- אין יומן HTTP, token מקומי, redirect HTTP של בקשות עם סוד, הדפסת גוף שגיאת ספק או העלאת מדיה. הודעות הכשל הן קודים קבועים. Desktop client_secret אינו סוד אפליקטיבי אמין כשלעצמו.
- נבדקו מסלול code→refresh→metadata→gh מדומה, callback מקומי אמיתי, בחירה שגויה, state, חשבון לא־בעלים, שיתוף, חסר token, scope רחב, כשלים ו־timeouts. אלה **אינם OAuth חי, בדיקת Windows או הצלחת Actions מול Drive**.

מקורות רשמיים שנבדקו ב־13.11.2026:

- [Picker עבור Desktop ו־Mobile — פרמטרים וחזרת picked_file_ids](https://developers.google.com/workspace/drive/picker/guides/desktop-mobile-picker) — עודכן אצל Google ב־12.10.2026.
- [בחירת Drive scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth).
- [OAuth ופקיעת refresh tokens](https://developers.google.com/identity/protocols/oauth2#expiration).
- [דרישות Branding ל־External Production](https://support.google.com/cloud/answer/15549049?hl=en).
