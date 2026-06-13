// bookbridge — macOS Vision OCR 工具
//
// 用 Apple Vision 框架做高质量文字识别，对中日韩与拉丁文字均佳，
// 完全在本地运行、免费、无需联网。
//
// 编译：  swiftc -O vision_ocr.swift -o vision_ocr
// 用法：  ./vision_ocr [--langs zh-Hans,en-US] <图片>...
//        每张 <名>.png 输出同名 <名>.txt，每行带归一化坐标前缀
//        [x,y,w,h]，便于下游按版面（自上而下、自左而右）重排。
//
// 竖排页（如中文古籍、扉页题字）Vision 可能无法正确排序，
// 这类页面建议交给带视觉能力的 AI 按原图重排，详见仓库 prompts/。

import Foundation
import Vision
import CoreImage

var langs = ["zh-Hans", "zh-Hant", "en-US"]
var inputs: [String] = []

var i = 1
let argv = CommandLine.arguments
while i < argv.count {
    let a = argv[i]
    if a == "--langs", i + 1 < argv.count {
        langs = argv[i + 1].split(separator: ",").map { String($0) }
        i += 2
    } else {
        inputs.append(a)
        i += 1
    }
}

guard !inputs.isEmpty else {
    FileHandle.standardError.write(
        "usage: vision_ocr [--langs zh-Hans,en-US] <image>...\n".data(using: .utf8)!)
    exit(1)
}

for path in inputs {
    let url = URL(fileURLWithPath: path)
    guard let ciImage = CIImage(contentsOf: url) else {
        FileHandle.standardError.write("cannot load \(path)\n".data(using: .utf8)!)
        continue
    }
    let handler = VNImageRequestHandler(ciImage: ciImage, options: [:])
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = langs
    request.usesLanguageCorrection = true
    do {
        try handler.perform([request])
    } catch {
        FileHandle.standardError.write("OCR failed \(path): \(error)\n".data(using: .utf8)!)
        continue
    }
    let observations = request.results ?? []
    // 先按垂直位置自上而下，再按水平位置自左而右
    let sorted = observations.sorted { a, b in
        let ay = a.boundingBox.midY, by = b.boundingBox.midY
        if abs(ay - by) > 0.012 { return ay > by }
        return a.boundingBox.minX < b.boundingBox.minX
    }
    var lines: [String] = []
    for obs in sorted {
        if let cand = obs.topCandidates(1).first {
            let r = obs.boundingBox
            let prefix = String(
                format: "[%.3f,%.3f,%.3f,%.3f] ", r.minX, r.minY, r.width, r.height)
            lines.append(prefix + cand.string)
        }
    }
    let outPath = url.deletingPathExtension().appendingPathExtension("txt")
    try? lines.joined(separator: "\n").write(
        to: outPath, atomically: true, encoding: .utf8)
    print("OK \(path) lines=\(lines.count)")
}
