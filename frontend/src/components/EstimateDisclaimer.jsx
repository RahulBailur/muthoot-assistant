/** Shown under every loan amount. The text comes from the server, in the reply's language. */
export default function EstimateDisclaimer({ text, lang }) {
  if (!text) return null;
  return (
    <p className="estimate-disclaimer" role="note" lang={lang}>
      {text}
    </p>
  );
}
