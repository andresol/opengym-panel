// One installation language. User-authored names and notes are not translated.
export const LANGUAGE = process.env.PANEL_LANGUAGE ?? 'en';

if (!['nb', 'en'].includes(LANGUAGE)) {
  throw new Error('Unsupported PANEL_LANGUAGE: choose nb or en');
}

export const text = (norwegian, english) => LANGUAGE === 'en' ? english : norwegian;
