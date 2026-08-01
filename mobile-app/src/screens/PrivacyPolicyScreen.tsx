import React from "react";
import { LegalDocumentLayout } from "../components/LegalDocumentLayout";
import { useLanguage } from "../i18n/LanguageContext";

// Accurate to what this app actually does: no account, no login, no phone number --
// just a cart stored locally on the device, and the product names in it sent to the
// recipe backend only to generate meal ideas. Written to reflect the real data flows
// in this codebase rather than generic boilerplate; replace with real legal copy
// before shipping to real users.
export function PrivacyPolicyScreen() {
  const { t, language } = useLanguage();

  const sections =
    language === "no"
      ? [
          {
            heading: "Hvilke data samler vi inn?",
            body: "Ingen kontoinformasjon i det hele tatt -- appen krever ikke pålogging. Det eneste som lagres er handlekurven din (varene du har lagt til), og den lagres kun lokalt på din egen enhet.",
          },
          {
            heading: "Hva bruker vi dataene til?",
            body: "Når du ber om middagsidéer, sender appen navnene på varene du har valgt til vår oppskrifts-tjeneste for å generere forslag. Ingenting knyttes til deg personlig -- det finnes ingen brukerkonto å knytte det til.",
          },
          {
            heading: "Hvor lenge lagrer vi dataene?",
            body: "Handlekurven blir liggende på enheten din til du selv tømmer den, sletter appen, eller trykker \"Slett mine data\" i appen.",
          },
          {
            heading: "Dine rettigheter",
            body: "Siden ingenting lagres på våre servere, har du full kontroll lokalt: \"Slett mine data\" i appen fjerner alt umiddelbart. Spørsmål kan rettes direkte til oss.",
          },
        ]
      : [
          {
            heading: "What data do we collect?",
            body: "No account information at all -- the app doesn't require logging in. The only thing stored is your cart (the products you've added), and it lives only locally on your own device.",
          },
          {
            heading: "What do we use it for?",
            body: "When you ask for meal ideas, the app sends the names of your selected products to our recipe service to generate suggestions. Nothing is tied to you personally -- there's no user account for it to be tied to.",
          },
          {
            heading: "How long do we keep it?",
            body: 'Your cart stays on your device until you clear it yourself, delete the app, or tap "Delete my data" in the app.',
          },
          {
            heading: "Your rights",
            body: 'Since nothing is stored on our servers, you have full control locally: "Delete my data" in the app removes everything immediately. Questions can be sent directly to us.',
          },
        ];

  return (
    <LegalDocumentLayout
      title={t.privacyPolicyTitle}
      lastUpdated={t.legalLastUpdated}
      sections={sections}
      testID="privacy-policy-screen"
    />
  );
}
