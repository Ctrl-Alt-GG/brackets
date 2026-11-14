import { createInstance } from 'i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import { initReactI18next } from 'react-i18next';

import { i18nOptions } from './locales';

/** The language of the pages players open: the one chosen with the switch, or the browser's. */
const i18n = createInstance();

void i18n
  .use(LanguageDetector)
  // Makes it the instance of every `useTranslation` outside an `I18nextProvider`.
  .use(initReactI18next)
  .init({
    ...i18nOptions,
    detection: {
      caches: ['localStorage'],
      lookupLocalStorage: 'bracket:language',
      order: ['localStorage', 'navigator'],
    },
  });

document.documentElement.lang = i18n.resolvedLanguage ?? 'en';
i18n.on('languageChanged', (language) => {
  document.documentElement.lang = language;
});
