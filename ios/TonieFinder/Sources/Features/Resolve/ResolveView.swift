import SwiftUI

struct ResolveView: View {
    @StateObject private var vm = ResolveViewModel()

    var body: some View {
        NavigationStack {
            VStack(spacing: 12) {
                HStack(spacing: 8) {
                    TextField("Tonie suchen", text: $vm.query)
                        .textFieldStyle(.roundedBorder)

                    Button("Suchen") {
                        vm.search()
                    }
                    .buttonStyle(.borderedProminent)
                }

                if vm.isLoading {
                    ProgressView("Suche läuft …")
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

                if let errorMessage = vm.errorMessage {
                    Text(errorMessage)
                        .foregroundStyle(.red)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

                List(vm.results) { item in
                    NavigationLink(value: item) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(item.title)
                            Text("Score: \(Int((item.score * 100).rounded()))%")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                .listStyle(.plain)
            }
            .padding()
            .navigationTitle("Resolve")
            .navigationDestination(for: ResolveItem.self) { item in
                PricingDetailView(item: item)
            }
        }
    }
}
