import SwiftUI

struct PricingDetailView: View {
    @StateObject private var vm: PricingDetailViewModel

    init(item: ResolveItem) {
        _vm = StateObject(wrappedValue: PricingDetailViewModel(item: item))
    }

    var body: some View {
        List {
            Section("Tonie") {
                Text(vm.item.title)
                Text(vm.item.tonieId)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Section("Zustand") {
                Picker("Condition", selection: $vm.condition) {
                    ForEach(TonieCondition.allCases) { condition in
                        Text(condition.rawValue).tag(condition)
                    }
                }
                .pickerStyle(.menu)

                Button("Neu laden") {
                    vm.load()
                }
                .buttonStyle(.bordered)
            }

            if vm.isLoading {
                Section {
                    ProgressView("Preise werden geladen …")
                }
            }

            if let errorMessage = vm.errorMessage {
                Section("Fehler") {
                    Text(errorMessage)
                        .foregroundStyle(.red)
                }
            }

            if let pricing = vm.pricing {
                Section("Pricing") {
                    PriceRow(title: "Sofortverkaufspreis", value: pricing.instant)
                    PriceRow(title: "Fairer Marktpreis", value: pricing.fair)
                    PriceRow(title: "Geduldspreis", value: pricing.patience)

                    if let sampleSize = pricing.sampleSize {
                        Text("Sample Size: \(sampleSize)")
                    }

                    if let effectiveSampleSize = pricing.effectiveSampleSize {
                        Text("Effektive Sample Size: \(effectiveSampleSize, specifier: "%.1f")")
                    }

                    if let source = pricing.source {
                        Text("Source: \(source)")
                    }

                    if let qualityTier = pricing.qualityTier {
                        Text("Quality Tier: \(qualityTier)")
                    }

                    if let confidenceScore = pricing.confidenceScore {
                        Text("Confidence: \(confidenceScore, specifier: "%.2f")")
                    }
                }
            }
        }
        .navigationTitle("Pricing")
        .toolbar(.visible, for: .tabBar)
        .task {
            vm.load()
        }
    }
}
