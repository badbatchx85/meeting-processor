//! Pure transitions for the first-run setup flow. The UI and commands drive
//! this; keeping it pure makes the flow unit-testable.
use serde::Serialize;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum SetupState {
    Detect,
    NeedsSetup,
    Installing,
    Bootstrap,
    Starting,
    Ready,
    Error,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Event {
    AllPresent,
    Missing,
    UserStartedSetup,
    InstallDone,
    BootstrapDone,
    ServerReady,
    Failed,
    Retry,
}

/// Compute the next state. Unknown (state, event) pairs stay put.
pub fn next_state(state: SetupState, event: Event) -> SetupState {
    use Event::*;
    use SetupState::*;
    match (state, event) {
        (Detect, AllPresent) => Starting,
        (Detect, Missing) => NeedsSetup,
        (NeedsSetup, UserStartedSetup) => Installing,
        (Installing, InstallDone) => Bootstrap,
        (Bootstrap, BootstrapDone) => Starting,
        (Starting, ServerReady) => Ready,
        (_, Failed) => Error,
        (Error, Retry) => Detect,
        (s, _) => s,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use Event::*;
    use SetupState::*;

    #[test]
    fn happy_path_when_all_present() {
        assert_eq!(next_state(Detect, AllPresent), Starting);
        assert_eq!(next_state(Starting, ServerReady), Ready);
    }

    #[test]
    fn setup_path_when_missing() {
        assert_eq!(next_state(Detect, Missing), NeedsSetup);
        assert_eq!(next_state(NeedsSetup, UserStartedSetup), Installing);
        assert_eq!(next_state(Installing, InstallDone), Bootstrap);
        assert_eq!(next_state(Bootstrap, BootstrapDone), Starting);
    }

    #[test]
    fn failure_from_any_state_goes_to_error() {
        assert_eq!(next_state(Installing, Failed), Error);
        assert_eq!(next_state(Bootstrap, Failed), Error);
        assert_eq!(next_state(Starting, Failed), Error);
    }

    #[test]
    fn retry_returns_to_detect() {
        assert_eq!(next_state(Error, Retry), Detect);
    }

    #[test]
    fn unknown_pair_is_noop() {
        assert_eq!(next_state(Ready, Missing), Ready);
    }
}
