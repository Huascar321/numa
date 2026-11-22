// Small stroked icons share the surrounding text color, including in high contrast.
const paths = {
  date: "M3 7h14M6 2v4m8-4v4M4 4h12a1 1 0 0 1 1 1v12H3V5a1 1 0 0 1 1-1Z",
  account: "M3 5h13v11H3zM3 7h13M12 10h5v3h-5z",
  payee: "M3 8l2-5h10l2 5M3 8h14M4 8v9h12V8M8 17v-5h4v5",
  category: "M3 3h7l7 7-7 7-7-7zM7 7h.01",
  memo: "M4 3h12v10l-4 4H4zM12 17v-4h4M7 7h6M7 10h4",
  outflow: "M4 15 15 4M7 4h8v8",
  inflow: "M15 4 4 15m0-8v8h8",
  save: "m3 10 4.5 4.5L17 5",
  another: "M3 10h12m-5-5 5 5-5 5",
  edit: "m4 12 8-8 3 3-8 8-4 1zM10 6l3 3",
} as const;

export function RegisterIcon({ name }: { name: keyof typeof paths }) {
  return (
    <svg
      className="register-icon"
      width="16"
      height="16"
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.65"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={paths[name]} />
    </svg>
  );
}
