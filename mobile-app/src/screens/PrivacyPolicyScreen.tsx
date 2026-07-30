import React from "react";
import { ScrollView, StyleSheet } from "react-native";
import { Text } from "../components/AppText";
import { useLanguage } from "../i18n/LanguageContext";
import { FONT_BOLD } from "../theme/typography";

// A placeholder policy covering exactly what this app actually does today (phone-
// number login, a local cart, no ad tracking) -- written to be accurate to the real
// data flows in this codebase rather than generic boilerplate copied from elsewhere.
// Replace with real legal copy before shipping to real users; this exists so the
// consent checkbox on the login screen has something genuine to link to.
export function PrivacyPolicyScreen() {
  const { language } = useLanguage();

  const sections =
    language === "no"
      ? [
          {
            heading: "Hvilke data samler vi inn?",
            body: "Telefonnummeret du logger inn med, og produktene du legger i handlekurven. Handlekurven lagres kun lokalt på enheten din.",
          },
          {
            heading: "Hva bruker vi dataene til?",
            body: "Telefonnummeret brukes bare til å logge deg inn (via engangskode på SMS). Vi bruker det ikke til markedsføring eller deler det med tredjeparter.",
          },
          {
            heading: "Hvor lenge lagrer vi dataene?",
            body: "Så lenge du er logget inn på denne enheten. Du kan slette all lagret data når du vil, se \"Slett mine data\" i appen.",
          },
          {
            heading: "Dine rettigheter",
            body: "Du kan når som helst be om å få dataene dine slettet via \"Slett mine data\", eller kontakte oss direkte.",
          },
        ]
      : [
          {
            heading: "What data do we collect?",
            body: "The phone number you log in with, and the products you add to your cart. Your cart is stored only locally on your device.",
          },
          {
            heading: "What do we use it for?",
            body: "Your phone number is only used to log you in (via a one-time SMS code). We don't use it for marketing or share it with third parties.",
          },
          {
            heading: "How long do we keep it?",
            body: 'For as long as you stay logged in on this device. You can delete all stored data at any time via "Delete my data" in the app.',
          },
          {
            heading: "Your rights",
            body: 'You can request deletion of your data at any time via "Delete my data", or by contacting us directly.',
          },
        ];

  return (
    <ScrollView contentContainerStyle={styles.container} testID="privacy-policy-screen">
      {sections.map((section) => (
        <React.Fragment key={section.heading}>
          <Text style={styles.heading}>{section.heading}</Text>
          <Text style={styles.body}>{section.body}</Text>
        </React.Fragment>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 16, backgroundColor: "#f5f5f5" },
  heading: { fontSize: 16, fontWeight: "700", fontFamily: FONT_BOLD, color: "#1a1a1a", marginTop: 16, marginBottom: 6 },
  body: { fontSize: 14, color: "#333", lineHeight: 20 },
});
