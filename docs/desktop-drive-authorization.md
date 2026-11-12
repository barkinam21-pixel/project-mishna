# חיבור חד־פעמי מ־Windows

הכלי הוא קובץ Python יחיד: `tools/authorize_private_drive.py`. הוא משתמש רק בספרייה התקנית. נדרשים Python3 ו־GitHub CLI מותקנים במחשב המבצע את האישור; לא הותקן דבר במחשב בר. אין להפעיל מתוך חלון משותף/הקלטת מסך או להדביק פרטי OAuth בצ׳אט.

1. ב־Google Auth Platform בדוק **Audience → Publishing status**. לאפליקציית External במצב Testing, refresh_token עם הרשאות Drive פג בדרך כלל אחרי שבעה ימים. העבר ל־**In production** לפני האישור הסופי. שינוי המצב אינו מחדש token ישן; הפק חדש לאחריו. הרשאות Drive עשויות לחייב verification, או להציג אזהרת אפליקציה לא מאומתת במסגרת חריג שימוש אישי. אין לעקוף אזהרה בחשבון שאינו שלך ואין להבטיח אישור Google. גם Production אינו מבטיח token נצחי: ביטול הסכמה, חוסר שימוש, מדיניות ארגונית ומגבלות token יכולים לבטלו.
2. הורד את JSON של **OAuth Client מסוג Desktop** שכבר יצרת. שמור בתיקייה פרטית מחוץ למאגר/OneDrive ציבורי. אין להעלות אותו ל־GitHub כקובץ.
3. אם GitHub CLI כבר מחובר לחשבונך, אין צורך להתחבר שוב. אחרת הרץ פעם אחת `gh auth login` ובחר כניסה דרך הדפדפן.
4. הרץ ב־PowerShell, בתיקיית הכלי:

```powershell
py authorize_private_drive.py "$env:USERPROFILE\Downloads\client_secret.json" --existing-files
```

יש להתאים את שם קובץ ה־JSON שהורדת. בדפדפן שייפתח בחר את חשבון הבעלים של שלושת הקבצים ואשר. לאחר מכן הכלי בודק את שלושת הקבצים ושומר ישירות את `MISHNAH_DRIVE_OAUTH_JSON` ב־GitHub באמצעות stdin, בלי להדפיס/לשמור token בקובץ. הוא אינו יוצר איורים או משנה את קובצי Drive. כשל בבדיקה מונע שמירת סוד חדש. אין להפעיל Transcript/דיבוג או לצלם את קובץ הלקוח.

## מדוע ההרשאה אינה מצומצמת לשלושה IDs

`drive.file` היא ההרשאה המצומצמת המועדפת, אבל היא נותנת לאפליקציה החדשה גישה לקבצים שנוצרו על ידה או שהמשתמש פתח/בחר עבורה. שלושת קובצי הפרויקט נוצרו באמצעות יישום אחר. רשימת IDs אינה מעניקה גישה. בלי Google Picker שמאפשר לבחור את שלושתם עבור אותו OAuth Client, אין scope המאפשר קריאה ועדכון של שלושה קבצים שרירותיים בלבד.

לכן **`--existing-files` הוא opt-in מפורש להרשאת `drive` המלאה**, הנחוצה למסלול הקיים ללא Picker. זו הרשאה רחבה ו־restricted, ואינה מוצגת כמינימלית מבחינת החשבון. ללא הדגל הכלי מבקש רק `drive.file`; הוא ייעצר אם הקבצים אינם זמינים. לא נוספה הרשאת Gmail/Cloud/זהות אחרת. חלופת drive.file+Picker דורשת ממשק בחירת קבצים והגדרות נוספות ואינה מיושמת בקובץ הזה. מי שאינו רוצה הרשאת Drive רחבה לא צריך להפעיל את מצב existing-files.

## אבטחה וגבולות

Authorization Code עם PKCE-S256, state אקראי, פורט פנוי על127.0.0.1 בלבד, timeout חמש דקות וללא יומןHTTP. סודות נשארים בזיכרון התהליך ונשלחים רק ל־Google OAuth ול־GitHub CLI המורשה. Desktop client_secret אינו סוד אפליקטיבי אמין בפני עצמו. GitHub CLI חייב הרשאה לשמירתSecrets במאגר; אין לעקוף403. שמירתSecret אינה מפעילה יצירה. בדיקתActions check עדיין נדרשת לאחר ההגדרה. הקוד נבדק ללא OAuth חי וללא מחשבWindows אמיתי; אישורGoogle ושמירתSecret לא בוצעו בסבב הזה.

מקורות Google: https://developers.google.com/identity/protocols/oauth2/native-app — https://developers.google.com/identity/protocols/oauth2#expiration — https://developers.google.com/workspace/drive/api/guides/api-specific-auth
