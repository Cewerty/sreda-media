# Проверка оформления CMS — #31

Снимки сделаны в Chrome на встроенных вымышленных данных прототипа.
`before` — main на коммите ff066af, `after` — правки этого PR.
Одинаковые размеры окна для сравнения: 1440 × 1000; главная и список
сняты целиком, форма — в пределах окна. Мобильная главная: 390 × 844.

| Экран | Светлая тема: до / после | Тёмная тема: до / после |
| --- | --- | --- |
| Главная | [До](dashboard-light-before.png) / [После](dashboard-light-after.png) | [До](dashboard-dark-before.png) / [После](dashboard-dark-after.png) |
| Кандидаты | [До](candidates-light-before.png) / [После](candidates-light-after.png) | [До](candidates-dark-before.png) / [После](candidates-dark-after.png) |
| Форма | [До](form-light-before.png) / [После](form-light-after.png) | [До](form-dark-before.png) / [После](form-dark-after.png) |
| Мобильная главная | [После](mobile-light-after.png) | [После](mobile-dark-after.png) |
| Мобильный редактор | [После](mobile-form-light-after.png) | [После](mobile-form-dark-after.png) |

## Проверки

Из корня репозитория успешно выполнены:

```sh
pnpm verify:cms
pnpm test:cms
pnpm check:cms
pnpm build:cms
```

45 тестов проходят. При съёмке настольных экранов не зарегистрированы ошибки JavaScript.
В обеих темах проверены фон и видимый фокус полей формы (результат в
[checks.json](checks.json)). На ширинах 320, 360, 390 и 430 px нет горизонтального переполнения
на главной, в списке кандидатов, карточке кандидата, отчёте и редакторе в обеих темах.
Проверен переход к списку через мобильное меню. Кнопки режима редактора
на узком экране расположены под заголовком, ссылки мобильного меню имеют высоту 44 px.
Проверка в Chrome не заменяет ревью и проверку остальных браузеров из NFR-COMPAT-01.
