import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("EvidRoute console", () => {
  it("renders the query workspace and risk controls", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: /know when to search/i })).toBeInTheDocument();
    expect(screen.getByLabelText("Research query")).toBeInTheDocument();
    expect(screen.getByText(/Unsupported-answer risk/i)).toBeInTheDocument();
  });

  it("switches verification modes without submitting", () => {
    render(<App />);
    const bestEffort = screen.getByRole("button", { name: "Best effort" });
    fireEvent.click(bestEffort);
    expect(bestEffort).toHaveClass("active");
  });
});
