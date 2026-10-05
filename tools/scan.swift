import Foundation
import AppKit
import Vision

// Usage: scan <page-image.jpg> <page-number> <assets-dir> <out.json>
//
// One pass over a scanned book page:
//   * OCR every text line with macOS Vision, recording normalised geometry
//   * segment the layout into blocks from row statistics
//   * classify each block as picture or text
//   * export each picture region as assets/images/page-NNN-K.jpg
//   * write {page, width, height, lines[], regions[], blocks[]} to out.json

let args = Array(CommandLine.arguments.dropFirst())
guard args.count >= 4 else {
    FileHandle.standardError.write("usage: scan <image> <page> <assetsDir> <out.json>\n".data(using: .utf8)!)
    exit(2)
}
let imagePath = args[0]
let pageNumber = Int(args[1]) ?? 0
let assetsDir = args[2]
let outPath = args[3]
let pageTag = String(format: "%03d", pageNumber)
try? FileManager.default.createDirectory(atPath: assetsDir, withIntermediateDirectories: true)

guard let nsImage = NSImage(contentsOfFile: imagePath),
      let cg = nsImage.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    FileHandle.standardError.write("cannot load \(imagePath)\n".data(using: .utf8)!)
    exit(1)
}
let width = cg.width
let height = cg.height

// ---------------------------------------------------------------- pixel data
var grey = [UInt8](repeating: 0, count: width * height)
grey.withUnsafeMutableBytes { raw in
    guard let space = CGColorSpace(name: CGColorSpace.linearGray),
          let ctx = CGContext(data: raw.baseAddress, width: width, height: height,
                              bitsPerComponent: 8, bytesPerRow: width, space: space,
                              bitmapInfo: CGImageAlphaInfo.none.rawValue) else { return }
    ctx.draw(cg, in: CGRect(x: 0, y: 0, width: width, height: height))
}

// ------------------------------------------------------------ row statistics
let darkCut: UInt8 = 190
let paperCut: UInt8 = 246

var rowMinX = [Int](repeating: width, count: height)
var rowMaxX = [Int](repeating: -1, count: height)
var rowInk = [Int](repeating: 0, count: height)
var rowRuns = [Int](repeating: 0, count: height)
var rowPaper = [Double](repeating: 0, count: height)

for y in 0..<height {
    let base = y * width
    var run = 0, ink = 0, runs = 0, paper = 0
    var mn = width, mx = -1
    for x in 0..<width {
        let v = grey[base + x]
        if v >= paperCut { paper += 1 }
        if v < darkCut {
            ink += 1
            run += 1
            if x < mn { mn = x }
            if x > mx { mx = x }
        } else {
            if run > 0 { runs += 1 }
            run = 0
        }
    }
    if run > 0 { runs += 1 }
    rowMinX[y] = mn; rowMaxX[y] = mx; rowInk[y] = ink
    rowRuns[y] = runs; rowPaper[y] = Double(paper) / Double(width)
}

func isTextRow(_ y: Int) -> Bool {
    if rowInk[y] == 0 { return false }
    let density = Double(rowInk[y]) / Double(width)
    if rowRuns[y] >= 20 { return true }
    if rowRuns[y] >= 12 && density < 0.25 { return true }
    return false
}

func extentsAgree(_ a: Int, _ b: Int) -> Bool {
    let l1 = rowMinX[a], r1 = rowMaxX[a], l2 = rowMinX[b], r2 = rowMaxX[b]
    if r1 < l1 || r2 < l2 { return false }
    let overlap = min(r1, r2) - max(l1, l2)
    let span = max(r1, r2) - min(l1, l2)
    if span <= 0 { return true }
    return Double(overlap) / Double(span) > 0.94
}

func rowsRepeat(_ a: Int, _ b: Int) -> Bool {
    rowInk[a] > 0 && rowInk[b] > 0 &&
    abs(rowMinX[a] - rowMinX[b]) <= 3 &&
    abs(rowMaxX[a] - rowMaxX[b]) <= 3 &&
    abs(rowInk[a] - rowInk[b]) <= 3
}

// ------------------------------------------------------------------- blocks
struct Block { var y0: Int, y1: Int, x0: Int, x1: Int, textRows: Int, inkedRows: Int }

var blocks: [Block] = []
var y = 0
while y < height {
    if rowInk[y] == 0 { y += 1; continue }
    var y1 = y
    var j = y
    while j + 1 < height {
        if rowInk[j + 1] == 0 {
            var k = j + 1
            var paper = false
            while k < height && rowInk[k] == 0 {
                if rowPaper[k] > 0.97 { paper = true; break }
                k += 1
            }
            let gap = k - j - 1
            if paper || k >= height || gap > 60 { break }
            if !extentsAgree(j, k) { break }
            j = k
            y1 = j
            continue
        }
        if !extentsAgree(j, j + 1) && !rowsRepeat(j, j + 1) { break }
        j += 1
        y1 = j
    }
    var x0 = width, x1 = -1, textRows = 0, inked = 0
    for k in y...y1 where rowInk[k] > 0 {
        if rowMinX[k] < x0 { x0 = rowMinX[k] }
        if rowMaxX[k] > x1 { x1 = rowMaxX[k] }
        inked += 1
        if isTextRow(k) { textRows += 1 }
    }
    if x1 >= x0 {
        blocks.append(Block(y0: y, y1: y1, x0: x0, x1: x1, textRows: textRows, inkedRows: inked))
    }
    y = y1 + 1
}

// ------------------------------------------- merge fragments of one picture
func overlapRatio(_ a: Block, _ b: Block) -> Double {
    let overlap = min(a.x1, b.x1) - max(a.x0, b.x0)
    let unionSpan = max(a.x1, b.x1) - min(a.x0, b.x0)
    if unionSpan <= 0 { return 1 }
    return Double(overlap) / Double(unionSpan)
}

var merging = true
while merging {
    merging = false
    outer: for i in 0..<blocks.count {
        for k in (i + 1)..<blocks.count {
            let a = blocks[i], b = blocks[k]
            let top = a.y1 < b.y0 ? a : b
            let bottom = a.y1 < b.y0 ? b : a
            let gap = bottom.y0 - top.y1 - 1
            if gap < 0 || gap > 150 { continue }
            if overlapRatio(a, b) < 0.80 { continue }
            // the separator must contain no ink at all, so that no text line
            // can ever be absorbed into a picture
            var inkBetween = false
            if top.y1 + 1 <= bottom.y0 - 1 {
                for row in (top.y1 + 1)...(bottom.y0 - 1) where rowInk[row] > 0 {
                    inkBetween = true
                    break
                }
            }
            if inkBetween { continue }
            let texts = Double(a.textRows + b.textRows)
            let inkeds = Double(a.inkedRows + b.inkedRows)
            if inkeds > 0 && texts / inkeds > 0.30 { continue }
            let union = Block(y0: min(a.y0, b.y0), y1: max(a.y1, b.y1),
                              x0: min(a.x0, b.x0), x1: max(a.x1, b.x1),
                              textRows: a.textRows + b.textRows,
                              inkedRows: a.inkedRows + b.inkedRows)
            blocks.remove(at: k)
            blocks.remove(at: i)
            blocks.append(union)
            merging = true
            break outer
        }
    }
}

// ------------------------------------------------------- picture extraction
struct Region { var y0: Int, y1: Int, x0: Int, x1: Int }

func looksLikeColourPad(_ r: Region) -> Bool {
    var total = 0, mid = 0
    for yy in r.y0...r.y1 {
        let base = yy * width
        for x in r.x0...r.x1 {
            let v = grey[base + x]
            total += 1
            if v > 30 && v < 225 { mid += 1 }
        }
    }
    return Double(mid) / Double(max(1, total)) > 0.80
}

func writeJPEG(_ image: CGImage, to path: String) -> Bool {
    let rep = NSBitmapImageRep(cgImage: image)
    guard let data = rep.representation(using: .jpeg, properties: [.compressionFactor: 0.86]) else { return false }
    return (try? data.write(to: URL(fileURLWithPath: path))) != nil
}

var regionRecords: [[String: Any]] = []
var regionIndex = 0

for block in blocks {
    let bh = block.y1 - block.y0 + 1
    let bw = block.x1 - block.x0 + 1
    if bw < 80 || bh < 80 { continue }
    let textFrac = Double(block.textRows) / Double(max(1, block.inkedRows))
    if textFrac > 0.30 { continue }
    if bh < 110 && bw > bh * 5 { continue }

    // trim to rows that actually contain ink
    var top = block.y0, bottom = block.y1
    while top < bottom && rowInk[top] == 0 { top += 1 }
    while bottom > top && rowInk[bottom] == 0 { bottom -= 1 }

    let pad = 6
    let x0 = max(0, block.x0 - pad), x1 = min(width - 1, block.x1 + pad)
    let yTop = max(0, top - pad), yBottom = min(height - 1, bottom + pad)
    let cw = x1 - x0 + 1, ch = yBottom - yTop + 1
    if cw < 80 || ch < 80 { continue }
    if Double(cw) * Double(ch) < 14000 { continue }   // ignore specks

    let rect = CGRect(x: x0, y: yTop, width: cw, height: ch)
    guard let crop = cg.cropping(to: rect) else { continue }
    let name = "page-\(pageTag)-\(regionIndex).jpg"
    guard writeJPEG(crop, to: assetsDir + "/" + name) else { continue }

    let region = Region(y0: yTop, y1: yBottom, x0: x0, x1: x1)

    // reject boxes that are essentially blank paper or a single line of
    // decorative type (a real picture fills its box with tone)
    var toned = 0, sampled = 0
    for yy in stride(from: yTop, through: yBottom, by: 2) {
        let base = yy * width
        for xx in stride(from: x0, through: x1, by: 2) {
            sampled += 1
            if grey[base + xx] < 238 { toned += 1 }
        }
    }
    if sampled > 0 && Double(toned) / Double(sampled) < 0.07 { continue }

    regionRecords.append([
        "file": name,
        "x": Double(x0) / Double(width),
        "y": Double(yTop) / Double(height),
        "w": Double(cw) / Double(width),
        "h": Double(ch) / Double(height),
        "px": cw,
        "py": ch,
        "pad": looksLikeColourPad(region),
    ])
    regionIndex += 1
}

// ---------------------------------------------------------------------- OCR
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true
request.recognitionLanguages = ["en-US"]

var lineRecords: [[String: Any]] = []
if let handler = Optional(VNImageRequestHandler(cgImage: cg, options: [:])) {
    do {
        try handler.perform([request])
        for observation in request.results ?? [] {
            guard let candidate = observation.topCandidates(1).first else { continue }
            let bb = observation.boundingBox
            lineRecords.append([
                "text": candidate.string,
                "x": bb.origin.x,
                // Vision's origin is bottom-left; store top-left for the layout pass
                "y": 1.0 - (bb.origin.y + bb.size.height),
                "w": bb.size.width,
                "h": bb.size.height,
                "conf": candidate.confidence,
            ])
        }
    } catch {
        FileHandle.standardError.write("ocr failed for page \(pageNumber)\n".data(using: .utf8)!)
    }
}

let payload: [String: Any] = [
    "page": pageNumber,
    "image": (imagePath as NSString).lastPathComponent,
    "width": width,
    "height": height,
    "lines": lineRecords,
    "regions": regionRecords,
]

guard let json = try? JSONSerialization.data(withJSONObject: payload, options: []) else { exit(1) }
try? json.write(to: URL(fileURLWithPath: outPath))
