// Amounts as customers read them: Indian digit grouping, whole rupees (₹2,47,500).
const rupeeFormat = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

export const rupees = (amount) => rupeeFormat.format(amount);

const dayFormat = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC", // a calendar date from the API ("2026-10-27") has no time of day
});

/** "2026-10-27" -> "27 Oct 2026" */
export const formatDay = (isoDate) => dayFormat.format(new Date(`${isoDate}T00:00:00Z`));
