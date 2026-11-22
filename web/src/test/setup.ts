import "@testing-library/jest-dom/vitest";

// JSDOM has no viewport scrolling; navigation scroll is exercised in Playwright.
window.scrollTo = () => {};
