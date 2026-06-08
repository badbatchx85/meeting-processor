//! Allocate a free localhost TCP port by binding to :0 and reading it back.
use std::net::{Ipv4Addr, TcpListener};

/// Returns an OS-assigned free port on 127.0.0.1. The listener is dropped
/// immediately, so there is a tiny race window — acceptable for a local
/// single-user app, and far safer than the old hardcoded 8765.
pub fn free_port() -> std::io::Result<u16> {
    let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0))?;
    Ok(listener.local_addr()?.port())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::{Ipv4Addr, TcpListener};

    #[test]
    fn returns_a_bindable_port() {
        let port = free_port().expect("should allocate");
        assert!(port > 0);
        TcpListener::bind((Ipv4Addr::LOCALHOST, port)).expect("port should be free");
    }

    #[test]
    fn successive_calls_usually_differ_or_are_valid() {
        let a = free_port().unwrap();
        let b = free_port().unwrap();
        assert!(a > 0 && b > 0);
    }
}
