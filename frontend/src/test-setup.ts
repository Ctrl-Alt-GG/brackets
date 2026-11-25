import { createInstance } from 'i18next';
import { initReactI18next } from 'react-i18next';

import { i18nOptions } from './app/locales';

// Unit tests read the English texts, from the instance that `getI18n` and `useTranslation` find,
// as the page's own instance is found in the browser.
await createInstance({ ...i18nOptions, lng: 'en' })
  .use(initReactI18next)
  .init();
