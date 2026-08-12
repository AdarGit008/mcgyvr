type Canvas = { rows: number; cols: number; cells: number[][] };

function checkRect(canvas: Canvas, rect: number[]): void {
  if (!Array.isArray(rect) || rect.length !== 4) {
    throw new Error("a rect is [top, left, bottom, right]");
  }
  for (const bound of rect) {
    if (!Number.isInteger(bound)) {
      throw new Error("rect bounds must be integers");
    }
  }
  const [top, left, bottom, right] = rect;
  if (top >= bottom || left >= right) {
    throw new Error("a rect must cover at least one cell");
  }
  if (top < 0 || left < 0 || bottom > canvas.rows || right > canvas.cols) {
    throw new Error("a rect must stay on the canvas");
  }
}

export function newCanvas(rows: number, cols: number): Canvas {
  if (!Number.isInteger(rows) || rows < 1 || !Number.isInteger(cols) || cols < 1) {
    throw new Error("canvas dimensions must be positive integers");
  }
  const cells: number[][] = [];
  for (let r = 0; r < rows; r += 1) {
    cells.push(new Array(cols).fill(0));
  }
  return { rows, cols, cells };
}

export function stampRect(canvas: Canvas, rect: number[]): number {
  checkRect(canvas, rect);
  const [top, left, bottom, right] = rect;
  let inked = 0;
  for (let r = top; r < bottom; r += 1) {
    for (let c = left; c < right; c += 1) {
      if (canvas.cells[r][c] === 0) {
        canvas.cells[r][c] = 1;
        inked += 1;
      }
    }
  }
  return inked;
}

export function inkTotal(canvas: Canvas): number {
  let total = 0;
  for (const row of canvas.cells) {
    for (const cell of row) {
      total += cell;
    }
  }
  return total;
}
