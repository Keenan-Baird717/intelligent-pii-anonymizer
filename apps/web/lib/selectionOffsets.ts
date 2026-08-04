/**
 * Map a browser Selection inside a source-text container to exact character
 * offsets in the original source string. Does not search by selected string.
 */

export type SourceOffsets = {
  start: number;
  end: number;
};

function isElement(node: Node): node is Element {
  return node.nodeType === Node.ELEMENT_NODE;
}

/**
 * Convert a Range boundary (node + offset) into a character offset within
 * `container`, counting only text-node characters in document order.
 */
export function boundaryToSourceOffset(
  container: Node,
  boundaryNode: Node,
  boundaryOffset: number,
): number | null {
  if (!container.contains(boundaryNode) && boundaryNode !== container) {
    return null;
  }

  // If the boundary is an element, convert to a text-node boundary.
  let node: Node | null = boundaryNode;
  let offset = boundaryOffset;

  if (isElement(node)) {
    if (offset <= 0) {
      // Before first child → find first text node descendant start, or start of element.
      const firstText = firstTextNode(node);
      if (!firstText) {
        // Empty element: offset is sum of all text before this element.
        return textLengthBeforeNode(container, node);
      }
      node = firstText;
      offset = 0;
    } else if (offset >= node.childNodes.length) {
      // After last child → end of last text descendant, or after element.
      const lastText = lastTextNode(node);
      if (!lastText) {
        return textLengthBeforeNode(container, node);
      }
      node = lastText;
      offset = lastText.data.length;
    } else {
      const child = node.childNodes[offset];
      const firstText = firstTextNode(child) ?? firstTextNodeAfter(container, child);
      if (!firstText) {
        return textContentLength(container);
      }
      node = firstText;
      offset = 0;
    }
  }

  if (node.nodeType !== Node.TEXT_NODE) {
    return null;
  }

  const textNode = node as Text;
  if (offset < 0 || offset > textNode.data.length) {
    return null;
  }

  return textLengthBefore(container, textNode) + offset;
}

function textLengthBefore(container: Node, targetTextNode: Text): number {
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  let total = 0;
  let current = walker.nextNode();
  while (current) {
    if (current === targetTextNode) {
      return total;
    }
    total += (current as Text).data.length;
    current = walker.nextNode();
  }
  return total;
}

/** Character length of all text nodes that appear before `target` in document order. */
function textLengthBeforeNode(container: Node, target: Node): number {
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  let total = 0;
  let current = walker.nextNode();
  while (current) {
    if (target === current || target.contains(current)) {
      return total;
    }
    // If current text node appears after target in document order, stop.
    const position = target.compareDocumentPosition(current);
    if (position & Node.DOCUMENT_POSITION_FOLLOWING) {
      return total;
    }
    total += (current as Text).data.length;
    current = walker.nextNode();
  }
  return total;
}

function textContentLength(container: Node): number {
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  let total = 0;
  let current = walker.nextNode();
  while (current) {
    total += (current as Text).data.length;
    current = walker.nextNode();
  }
  return total;
}

function firstTextNode(root: Node): Text | null {
  if (root.nodeType === Node.TEXT_NODE) {
    return root as Text;
  }
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  return walker.nextNode() as Text | null;
}

function lastTextNode(root: Node): Text | null {
  if (root.nodeType === Node.TEXT_NODE) {
    return root as Text;
  }
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let last: Text | null = null;
  let current = walker.nextNode();
  while (current) {
    last = current as Text;
    current = walker.nextNode();
  }
  return last;
}

function firstTextNodeAfter(container: Node, afterNode: Node): Text | null {
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  let current = walker.nextNode();
  let seen = false;
  while (current) {
    if (seen) {
      return current as Text;
    }
    if (afterNode.contains(current) || afterNode === current) {
      seen = true;
    }
    current = walker.nextNode();
  }
  return null;
}

/**
 * Map the current window selection to source offsets relative to `container`.
 * Returns null for empty/collapsed selections or selections outside the container.
 */
export function selectionToSourceOffsets(
  container: HTMLElement,
  selection: Selection | null = typeof window !== "undefined" ? window.getSelection() : null,
): SourceOffsets | null {
  if (!selection || selection.rangeCount === 0 || selection.isCollapsed) {
    return null;
  }

  const range = selection.getRangeAt(0);
  if (!container.contains(range.commonAncestorContainer)) {
    return null;
  }

  const start = boundaryToSourceOffset(container, range.startContainer, range.startOffset);
  const end = boundaryToSourceOffset(container, range.endContainer, range.endOffset);
  if (start === null || end === null || end <= start) {
    return null;
  }

  return { start, end };
}
