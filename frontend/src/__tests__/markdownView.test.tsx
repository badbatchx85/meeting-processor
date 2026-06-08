import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MarkdownView, stripWikilinks } from "../components/MarkdownView";

describe("stripWikilinks", () => {
  it("flattens aliased links to their alias", () => {
    expect(stripWikilinks("[[Tarefas - 2026-06-04|Tarefas]]")).toBe("Tarefas");
  });
  it("flattens bare links to their target", () => {
    expect(stripWikilinks("[[Transcricao]]")).toBe("Transcricao");
  });
  it("handles multiple links in a line", () => {
    expect(stripWikilinks("ver [[A|alfa]] e [[B]]")).toBe("ver alfa e B");
  });
  it("leaves plain markdown untouched", () => {
    expect(stripWikilinks("**bold** text")).toBe("**bold** text");
  });
});

describe("MarkdownView", () => {
  it("renders wikilink alias as readable text, not raw syntax", () => {
    render(<MarkdownView>{"Tarefas: [[Tarefas - x|Tarefas]]"}</MarkdownView>);
    expect(screen.getByText(/Tarefas: Tarefas/)).toBeInTheDocument();
    expect(screen.queryByText(/\[\[/)).not.toBeInTheDocument();
  });
});
