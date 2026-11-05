# Pristal-Pilot

**Pristal-Pilot by MrSkrenh** — русскоязычный менеджер Minecraft-серверов для Windows.

Первая версия включает профили серверов, запуск/остановку Java-процессов и встроенную консоль. Данные профилей хранятся отдельно в `%APPDATA%\Pristal-Pilot`.

## Запуск из исходников
Требуются Windows, Python 3.10+ и Java (Java 21 рекомендуется для современных версий Minecraft).

```powershell
python main.py
```

## Сборка установщика
Откройте вкладку **Actions** и запустите **Build Windows installer** через Run workflow. Готовый EXE появится в Artifacts. Для публикации в Releases создайте тег вида `v0.1.0`.

## Безопасность
Режим `online-mode=false` допускает подмену имён игроков. Используйте whitelist и надёжную авторизацию. Не открывайте сервер в интернет без настройки firewall и понимания port forwarding.

## Автор
Разработана MrSkrenh. Программа бесплатная.

- Discord: https://discord.gg/vywgQxyJt
- Twitch: https://www.twitch.tv/skrenhtv
- YouTube: https://www.youtube.com/@skrenh
- Поддержать автора: https://new.donatepay.ru/donate/1530153

Ошибки и предложения: GitHub Issues.
