import { afterEach, describe, expect, it } from "vitest";

import { boundaryToSourceOffset, selectionToSourceOffsets } from "@/lib/selectionOffsets";

afterEach(() => {
  document.body.innerHTML = "";
  window.getSelection()?.removeAllRanges();
});

function mountHighlighted(source: string, highlightRanges: Array<[number, number]>) {
  const container = document.createElement("p");
  let cursor = 0;
  for (const [start, end] of highlightRanges) {
    if (start > cursor) {
      container.appendChild(document.createTextNode(source.slice(cursor, start)));
    }
    const mark = document.createElement("mark");
    mark.appendChild(document.createTextNode(source.slice(start, end)));
    container.appendChild(mark);
    cursor = end;
  }
  if (cursor < source.length) {
    container.appendChild(document.createTextNode(source.slice(cursor)));
  }
  document.body.appendChild(container);
  return container;
}

function selectOffsets(container: HTMLElement, start: number, end: number) {
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  let remainingStart = start;
  let remainingEnd = end;
  let startNode: Text | null = null;
  let startOffset = 0;
  let endNode: Text | null = null;
  let endOffset = 0;
  let current = walker.nextNode() as Text | null;
  while (current) {
    const length = current.data.length;
    if (!startNode && remainingStart <= length) {
      startNode = current;
      startOffset = remainingStart;
    } else if (!startNode) {
      remainingStart -= length;
    }
    if (!endNode && remainingEnd <= length) {
      endNode = current;
      endOffset = remainingEnd;
      break;
    }
    if (!endNode) {
      remainingEnd -= length;
    }
    if (startNode && !endNode) {
      // continue until end found
    }
    current = walker.nextNode() as Text | null;
  }
  if (!startNode || !endNode) {
    throw new Error("Unable to build test selection");
  }
  const range = document.createRange();
  range.setStart(startNode, startOffset);
  range.setEnd(endNode, endOffset);
  const selection = window.getSelection();
  selection?.removeAllRanges();
  selection?.addRange(range);
}

describe("selectionToSourceOffsets", () => {
  it("maps the second identical occurrence, not the first", () => {
    const source = "alpha alpha alpha";
    // highlight first alpha only
    const container = mountHighlighted(source, [[0, 5]]);
    // Select the second "alpha" at offsets 6-11
    selectOffsets(container, 6, 11);
    const offsets = selectionToSourceOffsets(container);
    expect(offsets).toEqual({ start: 6, end: 11 });
    expect(source.slice(offsets!.start, offsets!.end)).toBe("alpha");
  });

  it("maps the third identical occurrence across mark boundaries", () => {
    const source = "foo foo foo";
    const container = mountHighlighted(source, [
      [0, 3],
      [4, 7],
    ]);
    selectOffsets(container, 8, 11);
    const offsets = selectionToSourceOffsets(container);
    expect(offsets).toEqual({ start: 8, end: 11 });
    expect(source.slice(8, 11)).toBe("foo");
  });

  it("handles selection starting inside a highlight mark", () => {
    const source = "Hello fictional world";
    const container = mountHighlighted(source, [[6, 15]]); // "fictional"
    selectOffsets(container, 8, 15); // "ctional"
    const offsets = selectionToSourceOffsets(container);
    expect(offsets).toEqual({ start: 8, end: 15 });
    expect(source.slice(8, 15)).toBe("ctional");
  });

  it("returns null for collapsed selection", () => {
    const source = "only once";
    const container = mountHighlighted(source, []);
    selectOffsets(container, 2, 2);
    expect(selectionToSourceOffsets(container)).toBeNull();
  });

  it("returns null when selection is outside the container", () => {
    const container = mountHighlighted("inside text", []);
    const outside = document.createElement("div");
    outside.textContent = "outside";
    document.body.appendChild(outside);
    const range = document.createRange();
    range.selectNodeContents(outside);
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);
    expect(selectionToSourceOffsets(container)).toBeNull();
  });

  it("handles unicode characters with code-point offsets matching JS string indices", () => {
    const source = "café café";
    const container = mountHighlighted(source, [[0, 4]]);
    selectOffsets(container, 5, 9);
    const offsets = selectionToSourceOffsets(container);
    expect(offsets).toEqual({ start: 5, end: 9 });
    expect(source.slice(5, 9)).toBe("café");
  });
});

describe("boundaryToSourceOffset", () => {
  it("counts text across nested marks", () => {
    const source = "abXXXcd";
    const container = mountHighlighted(source, [[2, 5]]);
    const mark = container.querySelector("mark");
    const textNode = mark?.firstChild as Text;
    expect(boundaryToSourceOffset(container, textNode, 1)).toBe(3);
  });
});
