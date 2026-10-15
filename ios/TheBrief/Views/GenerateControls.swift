import SwiftUI

/// The section page's "Generate a new issue", and for Three Companies "Write
/// about a company" — web/components/GenerateButton.tsx and CompanyRequest.tsx.
@MainActor
struct GenerateControls: View {
    let section: NewsSection

    private enum Pending { case issue, company(String) }
    private enum Status: Equatable {
        case idle, busy, done(String), failed(String)
    }

    @State private var status: Status = .idle
    @State private var company = ""
    @State private var pending: Pending?
    @State private var askPassword = false
    @State private var password = ""
    @FocusState private var companyFocused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Button { run(.issue) } label: {
                Label(status == .busy && !isCompany ? "Generating…" : "Generate a new issue",
                      systemImage: "sparkles")
                    .font(.subheadline.weight(.semibold))
            }
            .buttonStyle(.bordered)
            .buttonBorderShape(.capsule)
            .disabled(status == .busy)

            if section.key == .stocks {
                VStack(alignment: .leading, spacing: 8) {
                    Eyebrow("Write about a company")
                    HStack(spacing: 8) {
                        TextField("Ticker or name, e.g. NVDA or Toyota", text: $company)
                            .textInputAutocapitalization(.characters)
                            .autocorrectionDisabled()
                            .submitLabel(.go)
                            .focused($companyFocused)
                            .onSubmit(submitCompany)
                            .padding(.horizontal, 14)
                            .frame(height: 44)
                            .background(.quaternary.opacity(0.6), in: RoundedRectangle(cornerRadius: 12))
                        Button("Write", action: submitCompany)
                            .buttonStyle(.borderedProminent)
                            .buttonBorderShape(.capsule)
                            .disabled(status == .busy || company.trimmingCharacters(in: .whitespaces).isEmpty)
                    }
                }
            }

            switch status {
            case let .done(message):
                Label(message, systemImage: "checkmark.circle.fill")
                    .font(.footnote).foregroundStyle(Color.brandAccent)
            case let .failed(message):
                Label(message, systemImage: "exclamationmark.triangle.fill")
                    .font(.footnote).foregroundStyle(.red)
            default:
                EmptyView()
            }
        }
        .alert("Site password", isPresented: $askPassword) {
            SecureField("Password", text: $password)
            Button("Cancel", role: .cancel) { password = ""; pending = nil }
            Button("Sign In") { signInAndRun() }
        } message: {
            Text("Generating spends credits, so it is behind the website's password. It is asked for once.")
        }
    }

    private var isCompany: Bool { if case .company = pending { return true } else { return false } }

    private func submitCompany() {
        let name = company.trimmingCharacters(in: .whitespaces)
        guard !name.isEmpty else { return }
        companyFocused = false
        run(.company(name))
    }

    private func run(_ action: Pending) {
        pending = action
        status = .busy
        Task {
            do {
                let message: String
                switch action {
                case .issue: message = try await GenerateClient.generate(section: section.key)
                case let .company(name): message = try await GenerateClient.generate(section: .stocks, company: name)
                }
                if case .company = action { company = "" }
                pending = nil
                status = .done(message)
                UINotificationFeedbackGenerator().notificationOccurred(.success)
            } catch GenerateClient.Failure.needsPassword {
                status = .idle
                askPassword = true
            } catch {
                pending = nil
                status = .failed(error.localizedDescription)
                UINotificationFeedbackGenerator().notificationOccurred(.error)
            }
        }
    }

    private func signInAndRun() {
        let entered = password
        password = ""
        guard let action = pending else { return }
        status = .busy
        Task {
            do {
                try await GenerateClient.signIn(entered)
                run(action)
            } catch {
                pending = nil
                status = .failed(error.localizedDescription)
            }
        }
    }
}
